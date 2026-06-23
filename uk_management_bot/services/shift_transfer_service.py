"""
Сервис передачи смен между исполнителями (REG-02, перестроен).

Работает на РЕАЛЬНОЙ ORM-модели `ShiftTransfer` (peer-to-peer:
shift_id / from_executor_id / to_executor_id, status-машина
pending→assigned→accepted/rejected/cancelled/completed/expired).

Два флоу:
  1) executor-инициированный с менеджерским посредничеством и приёмом
     (create_transfer → assign_transfer → accept_transfer/reject_transfer);
  2) менеджерский прямой reassign (reassign_shift, record_history=True) —
     вызывается ботом и веб-API.

Общее ядро `reassign_shift` меняет владельца смены + переносит активные заявки
старого исполнителя новому (status-preserving, через AssignmentService) и
ВОЗВРАЩАЕТ notification_jobs БЕЗ commit — владелец коммитит и рассылает.

`from/to_executor_id` — ВСЕГДА внутренний `users.id` (никогда telegram_id).
"""

from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Any
import json
import logging

from sqlalchemy.orm import Session, joinedload

from uk_management_bot.database.models.shift import Shift
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.shift_assignment import ShiftAssignment
from uk_management_bot.database.models.shift_transfer import ShiftTransfer as ShiftTransferModel
from uk_management_bot.services.notification_service import NotificationService
from uk_management_bot.utils.specializations import has_required_specs

logger = logging.getLogger(__name__)

# Активные статусы заявки, которые переносятся вместе со сменой (status-preserving).
ACTIVE_REQUEST_STATUSES = ["В работе", "Закуп", "Уточнение"]

# Статусы передачи, блокирующие создание новой передачи на ту же смену.
_BLOCKING_TRANSFER_STATUSES = ["pending", "assigned", "accepted"]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _has_role(user: User, role: str) -> bool:
    """Толерантный разбор `User.roles` (JSON-массив строк / CSV / скаляр)."""
    raw = getattr(user, "roles", None)
    if not raw:
        return False
    if isinstance(raw, (list, tuple, set)):
        return role in {str(r).strip() for r in raw}
    text = str(raw).strip()
    if text.startswith("["):
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return role in {str(r).strip() for r in parsed}
        except (json.JSONDecodeError, TypeError):
            pass
    return role in {part.strip() for part in text.split(",")}


class ShiftTransferService:
    """Сервис управления передачей смен между исполнителями."""

    def __init__(self, db: Session):
        self.db = db
        self.notification_service = NotificationService(db)

    # ========== ВАЛИДАЦИЯ ЦЕЛЕВОГО ИСПОЛНИТЕЛЯ ==========

    def _validate_reassign_target(self, shift: Shift, new_executor_id: int) -> Optional[str]:
        """Проверяет, можно ли переназначить `shift` на `new_executor_id`.

        Возвращает None если ок, иначе короткий error-key (handlers/web локализуют):
        executor_not_found / not_approved / not_executor / same_executor /
        spec_mismatch / overlap / shift_not_transferable.
        """
        # Смену без владельца или в терминальном статусе переназначать нельзя
        # (запись истории требует from_executor_id NOT NULL; completed/cancelled
        # — нет активной смены для передачи). UI показывает кнопку только для
        # planned/active с владельцем, но slash/API/гонка могут прийти иначе.
        if shift.user_id is None or shift.status not in ("planned", "active"):
            return "shift_not_transferable"
        new_executor = self.db.query(User).filter(User.id == new_executor_id).first()
        if not new_executor:
            return "executor_not_found"
        if new_executor.status != "approved":
            return "not_approved"
        if not _has_role(new_executor, "executor"):
            return "not_executor"
        if shift.user_id == new_executor_id:
            return "same_executor"
        if not has_required_specs(new_executor, shift):
            return "spec_mismatch"
        # Overlap: у нового исполнителя нет пересекающейся смены (active/planned).
        if shift.start_time is not None and shift.end_time is not None:
            overlap = self.db.query(Shift).filter(
                Shift.user_id == new_executor_id,
                Shift.status.in_(["active", "planned"]),
                Shift.id != shift.id,
                Shift.start_time < shift.end_time,
                Shift.end_time > shift.start_time,
            ).first()
            if overlap:
                return "overlap"
        return None

    # ========== ПЕРЕНОС АКТИВНЫХ ЗАЯВОК (status-preserving) ==========

    def _move_active_requests(self, shift: Shift, old_executor_id: int, new_executor_id: int) -> int:
        """Переносит активные заявки смены old→new БЕЗ смены статуса. Без commit.

        Основной скоуп — не-терминальные ShiftAssignment этой смены; fallback по
        Request.executor_id только для active-смены без проставленных привязок.
        Переносятся только заявки в активных статусах (В работе/Закуп/Уточнение).
        """
        from uk_management_bot.services.assignment_service import AssignmentService

        assignment_svc = AssignmentService(self.db)

        sa_rows = self.db.query(ShiftAssignment).filter(
            ShiftAssignment.shift_id == shift.id,
            ShiftAssignment.status.notin_(["completed", "cancelled"]),
        ).all()
        request_numbers = {row.request_number for row in sa_rows}

        if not request_numbers and shift.status == "active":
            fallback_reqs = self.db.query(Request).filter(
                Request.executor_id == old_executor_id,
                Request.status.in_(ACTIVE_REQUEST_STATUSES),
            ).all()
            request_numbers = {r.request_number for r in fallback_reqs}

        moved = 0
        for request_number in request_numbers:
            req = self.db.query(Request).filter(
                Request.request_number == request_number
            ).first()
            if req and req.status in ACTIVE_REQUEST_STATUSES:
                if assignment_svc.reassign_executor(request_number, new_executor_id):
                    moved += 1
        return moved

    # ========== ОБЩЕЕ ЯДРО: ПЕРЕНАЗНАЧЕНИЕ СМЕНЫ ==========

    def reassign_shift(
        self,
        shift_id: int,
        new_executor_id: int,
        actor_manager_id: Optional[int],
        *,
        record_history: bool,
    ) -> Dict[str, Any]:
        """Переназначает смену + переносит активные заявки. БЕЗ commit.

        Возвращает {success, error, notification_jobs, moved_requests}.
        notification_jobs — список (user_id, title, message); владелец рассылает
        ПОСЛЕ commit (иначе можно уведомить о переносе, который откатился).
        """
        shift = self.db.query(Shift).filter(Shift.id == shift_id).first()
        if not shift:
            return {"success": False, "error": "shift_not_found", "notification_jobs": []}

        error = self._validate_reassign_target(shift, new_executor_id)
        if error:
            return {"success": False, "error": error, "notification_jobs": []}

        old_executor_id = shift.user_id
        shift.user_id = new_executor_id
        moved = self._move_active_requests(shift, old_executor_id, new_executor_id)

        if record_history:
            now = _utcnow()
            self.db.add(ShiftTransferModel(
                shift_id=shift.id,
                from_executor_id=old_executor_id,
                to_executor_id=new_executor_id,
                assigned_by=actor_manager_id,
                status="completed",
                reason="manager_reassign",
                auto_assigned=True,
                assigned_at=now,
                responded_at=now,
                completed_at=now,
            ))

        shift_label = self._shift_label(shift)
        jobs: List[tuple] = [
            (new_executor_id, "Вам назначена смена",
             f"Вам переназначена смена {shift_label}. Активных заявок перенесено: {moved}."),
        ]
        if old_executor_id and old_executor_id != new_executor_id:
            jobs.append((
                old_executor_id, "Смена переназначена",
                f"Смена {shift_label} переназначена другому исполнителю.",
            ))

        return {
            "success": True,
            "error": None,
            "notification_jobs": jobs,
            "moved_requests": moved,
        }

    # ========== EXECUTOR-ИНИЦИИРОВАННЫЙ ФЛОУ ==========

    def create_transfer(
        self,
        shift_id: int,
        from_executor_id: int,
        reason: str,
        comment: str,
        urgency_level: str,
    ) -> Dict[str, Any]:
        """Создаёт передачу (status=pending). from_executor_id — внутренний users.id."""
        try:
            shift = self.db.query(Shift).filter(Shift.id == shift_id).first()
            if not shift:
                return {"success": False, "error": "shift_not_found"}
            if shift.user_id != from_executor_id:
                return {"success": False, "error": "not_your_shift"}
            if shift.status not in ("planned", "active"):
                return {"success": False, "error": "shift_not_transferable"}

            existing = self.db.query(ShiftTransferModel).filter(
                ShiftTransferModel.shift_id == shift_id,
                ShiftTransferModel.status.in_(_BLOCKING_TRANSFER_STATUSES),
            ).first()
            if existing:
                return {"success": False, "error": "transfer_already_exists"}

            transfer = ShiftTransferModel(
                shift_id=shift_id,
                from_executor_id=from_executor_id,
                status="pending",
                reason=reason or "other",
                comment=comment or None,
                urgency_level=urgency_level or "normal",
            )
            self.db.add(transfer)
            self.db.commit()
            self.db.refresh(transfer)

            # Уведомить менеджеров (best-effort, после commit).
            self.notify_managers_new_transfer(transfer)

            return {"success": True, "error": None, "transfer_id": transfer.id}
        except Exception as e:
            logger.error(f"create_transfer: ошибка: {e}")
            self.db.rollback()
            return {"success": False, "error": "internal_error"}

    def assign_transfer(
        self, transfer_id: int, to_executor_id: int, manager_id: int
    ) -> Dict[str, Any]:
        """Менеджер назначает получателя: pending→assigned. Без смены shift.user_id."""
        try:
            transfer = self.db.query(ShiftTransferModel).filter(
                ShiftTransferModel.id == transfer_id
            ).with_for_update().first()
            if not transfer:
                return {"success": False, "error": "transfer_not_found"}
            if transfer.status != "pending":
                return {"success": False, "error": "wrong_status"}
            if not transfer.can_be_assigned_to(to_executor_id):
                return {"success": False, "error": "cannot_assign_to_self"}

            shift = self.db.query(Shift).filter(Shift.id == transfer.shift_id).first()
            if not shift:
                return {"success": False, "error": "shift_not_found"}

            # Precheck guards (тот же набор, что accept перепроверит из-за гонки).
            error = self._validate_reassign_target(shift, to_executor_id)
            if error:
                return {"success": False, "error": error}

            if not transfer.update_status("assigned"):
                return {"success": False, "error": "wrong_status"}
            transfer.to_executor_id = to_executor_id
            transfer.assigned_by = manager_id
            self.db.commit()

            return {"success": True, "error": None, "transfer_id": transfer.id,
                    "to_executor_id": to_executor_id}
        except Exception as e:
            logger.error(f"assign_transfer: ошибка: {e}")
            self.db.rollback()
            return {"success": False, "error": "internal_error"}

    def accept_transfer(self, transfer_id: int, executor_id: int) -> Dict[str, Any]:
        """Получатель принимает: assigned→accepted→completed + перенос смены/заявок."""
        try:
            transfer = self.db.query(ShiftTransferModel).filter(
                ShiftTransferModel.id == transfer_id
            ).with_for_update().first()
            if not transfer:
                return {"success": False, "error": "transfer_not_found"}
            if transfer.status != "assigned":
                return {"success": False, "error": "wrong_status"}
            if transfer.to_executor_id != executor_id:
                return {"success": False, "error": "not_your_transfer"}

            # Транзишен accepted, затем перенос через общее ядро (без истории —
            # сама строка передачи и есть история).
            if not transfer.update_status("accepted"):
                return {"success": False, "error": "wrong_status"}

            res = self.reassign_shift(
                shift_id=transfer.shift_id,
                new_executor_id=executor_id,
                actor_manager_id=transfer.assigned_by,
                record_history=False,
            )
            if not res["success"]:
                # Откатываем промежуточный accepted — «висячего accepted» нет.
                self.db.rollback()
                return {"success": False, "error": res["error"]}

            transfer.update_status("completed")
            self.db.commit()

            # Уведомления ПОСЛЕ commit.
            jobs = list(res["notification_jobs"])
            jobs.append((
                transfer.from_executor_id, "Передача смены принята",
                "Назначенный исполнитель принял переданную смену.",
            ))
            if transfer.assigned_by:
                jobs.append((
                    transfer.assigned_by, "Передача смены принята",
                    f"Передача смены #{transfer.id} принята исполнителем.",
                ))
            self.dispatch_jobs(jobs)

            return {"success": True, "error": None, "moved_requests": res.get("moved_requests", 0)}
        except Exception as e:
            logger.error(f"accept_transfer: ошибка: {e}")
            self.db.rollback()
            return {"success": False, "error": "internal_error"}

    def reject_transfer(
        self, transfer_id: int, executor_id: int, comment: Optional[str] = None
    ) -> Dict[str, Any]:
        """Получатель отклоняет: assigned→rejected. Смена НЕ менялась."""
        try:
            transfer = self.db.query(ShiftTransferModel).filter(
                ShiftTransferModel.id == transfer_id
            ).with_for_update().first()
            if not transfer:
                return {"success": False, "error": "transfer_not_found"}
            if transfer.status != "assigned":
                return {"success": False, "error": "wrong_status"}
            if transfer.to_executor_id != executor_id:
                return {"success": False, "error": "not_your_transfer"}

            if not transfer.update_status("rejected", comment):
                return {"success": False, "error": "wrong_status"}
            self.db.commit()

            jobs = [(
                transfer.from_executor_id, "Передача смены отклонена",
                "Назначенный исполнитель отклонил переданную смену.",
            )]
            if transfer.assigned_by:
                jobs.append((
                    transfer.assigned_by, "Передача смены отклонена",
                    f"Передача смены #{transfer.id} отклонена получателем.",
                ))
            self.dispatch_jobs(jobs)

            return {"success": True, "error": None}
        except Exception as e:
            logger.error(f"reject_transfer: ошибка: {e}")
            self.db.rollback()
            return {"success": False, "error": "internal_error"}

    # ========== ВЫБОРКИ ДЛЯ ХЕНДЛЕРОВ ==========

    def list_pending_transfers(self, limit: int = 20) -> List[ShiftTransferModel]:
        """Ожидающие назначения передачи (для менеджера)."""
        return self.db.query(ShiftTransferModel).filter(
            ShiftTransferModel.status == "pending"
        ).options(
            joinedload(ShiftTransferModel.shift),
            joinedload(ShiftTransferModel.from_executor),
        ).order_by(ShiftTransferModel.created_at.desc()).limit(limit).all()

    def get_shift(self, shift_id: int) -> Optional[Shift]:
        return self.db.query(Shift).filter(Shift.id == shift_id).first()

    def list_eligible_executors(
        self, exclude_user_id: Optional[int], limit: int = 30, shift: Optional[Shift] = None
    ) -> List[User]:
        """Approved-исполнители для назначения/reassign (кроме указанного user.id).

        CR-1: при переданном ``shift`` префильтруем по спец-ии (``has_required_specs``),
        чтобы picker не показывал заведомо невалидных кандидатов, которых
        ``assign_transfer``/``reassign_shift`` всё равно отклонят по ``spec_mismatch``.
        Фильтр в Python ПОСЛЕ выборки → ``limit`` применяем после него.
        """
        users = self.db.query(User).filter(
            User.roles.contains("executor"),
            User.status == "approved",
            User.id != exclude_user_id,
        ).order_by(User.first_name).all()
        if shift is not None:
            from uk_management_bot.utils.specializations import has_required_specs
            users = [u for u in users if has_required_specs(u, shift)]
        return users[:limit]

    def manager_direct_reassign(
        self, shift_id: int, new_executor_id: int, actor_telegram_id: int
    ) -> Dict[str, Any]:
        """Прямой менеджерский reassign (бот): reassign_shift + commit (owner-слой).

        Резолвит менеджера по telegram_id, переназначает смену с записью истории,
        коммитит при успехе и ВОЗВРАЩАЕТ notification_jobs — рассылку выполняет
        вызывающий через `dispatch_jobs` ПОСЛЕ commit.
        """
        manager = self.db.query(User).filter(User.telegram_id == actor_telegram_id).first()
        res = self.reassign_shift(
            shift_id, new_executor_id,
            actor_manager_id=(manager.id if manager else None),
            record_history=True,
        )
        if res["success"]:
            self.db.commit()
        return res

    def get_transfer(self, transfer_id: int) -> Optional[ShiftTransferModel]:
        return self.db.query(ShiftTransferModel).filter(
            ShiftTransferModel.id == transfer_id
        ).options(
            joinedload(ShiftTransferModel.shift),
            joinedload(ShiftTransferModel.from_executor),
            joinedload(ShiftTransferModel.to_executor),
        ).first()

    def notify_managers_new_transfer(self, transfer: ShiftTransferModel) -> None:
        """Best-effort уведомление approved-менеджеров о новой передаче."""
        try:
            managers = self.db.query(User).filter(
                User.roles.contains("manager"),
                User.status == "approved",
            ).all()
            for manager in managers:
                self.notification_service.notify_user(
                    manager.id,
                    "Новая передача смены",
                    f"Поступила передача смены #{transfer.id}, ожидает назначения исполнителя "
                    f"(/assign_{transfer.id}).",
                )
        except Exception as e:
            logger.warning(f"notify_managers_new_transfer: {e}")

    # ========== ВСПОМОГАТЕЛЬНОЕ ==========

    def _shift_label(self, shift: Shift) -> str:
        if shift.start_time is not None:
            try:
                return f"#{shift.id} ({shift.start_time.strftime('%d.%m %H:%M')})"
            except Exception:
                pass
        return f"#{shift.id}"

    def dispatch_jobs(self, jobs: List[tuple]) -> None:
        """Best-effort рассылка (user_id, title, message) — строго ПОСЛЕ commit.

        Публичный: вызывается владельцем транзакции (бот-хендлер прямого reassign)
        после commit, а также внутри accept/reject.
        """
        for user_id, title, message in jobs:
            try:
                self.notification_service.notify_user(user_id, title, message)
            except Exception as e:
                logger.warning(f"_dispatch: ошибка уведомления user_id={user_id}: {e}")

    # ========== ПЛАНИРОВЩИК: ИСТЕКШИЕ ПЕРЕДАЧИ (BUG-BOT-036) ==========

    async def process_expired_transfers(self, hours_threshold: int = 24) -> Dict[str, Any]:
        """
        Помечает «зависшие» передачи как expired.

        Передача считается истёкшей, если её статус всё ещё «pending» / «assigned»,
        а с момента создания прошло больше `hours_threshold` часов.

        Returns:
            Dict с ключами:
              - processed_count: количество помеченных как expired записей (по факту commit)
              - scheduled_count: количество сформированных уведомлений (после commit)
              - delivered_count: количество фактически доставленных уведомлений
              - notified_count: алиас delivered_count (фактически доставлено)
              - errors: количество ошибок при обработке отдельных записей

        BUG-BOT-036: отправка уведомлений выполняется строго ПОСЛЕ успешного
        commit (чтобы не уведомлять об истечении передачи, которая не сохранилась),
        с per-job изоляцией; delivered отражает реальную доставку, не scheduling.
        """
        processed_count = 0
        scheduled_count = 0
        delivered_count = 0
        errors = 0
        jobs: list[tuple[int, str, str]] = []

        def _result() -> Dict[str, Any]:
            return {
                "processed_count": processed_count,
                "scheduled_count": scheduled_count,
                "delivered_count": delivered_count,
                "notified_count": delivered_count,
                "errors": errors,
            }

        # --- Фаза 1+2: мутация записей + commit (под rollback-guard) ---
        try:
            cutoff = _utcnow() - timedelta(hours=hours_threshold)

            expired_rows = self.db.query(ShiftTransferModel).filter(
                ShiftTransferModel.status.in_(["pending", "assigned"]),
                ShiftTransferModel.created_at < cutoff,
            ).all()

            if not expired_rows:
                logger.info("Истёкших передач не обнаружено")
                return _result()

            now = _utcnow()
            for transfer in expired_rows:
                try:
                    transfer.status = "expired"
                    transfer.responded_at = now
                    transfer.completed_at = now
                    transfer.comment = (
                        (transfer.comment or "")
                        + f"\n[{now.strftime('%Y-%m-%d %H:%M')}] Истекло автоматически (>{hours_threshold}ч без ответа)"
                    ).strip()
                    processed_count += 1
                    jobs.append((
                        transfer.from_executor_id,
                        "Передача смены истекла",
                        f"Передача смены #{transfer.id} помечена как истёкшая после "
                        f"{hours_threshold} ч без ответа.",
                    ))
                except Exception as row_err:
                    logger.error(
                        "Ошибка обработки истёкшей передачи %s: %s",
                        getattr(transfer, "id", "?"),
                        row_err,
                    )
                    errors += 1

            self.db.commit()
        except Exception as e:
            logger.error(f"Ошибка обработки истёкших передач: {e}")
            self.db.rollback()
            # Откат => ничего не обработано и не отправлено.
            processed_count = 0
            scheduled_count = 0
            delivered_count = 0
            errors += 1
            return _result()

        # --- Фаза 3: доставка ПОСЛЕ успешного commit, вне rollback-guard,
        # с изоляцией каждого job (ошибка доставки не трогает processed_count). ---
        scheduled_count = len(jobs)
        for user_id, title, message in jobs:
            try:
                if await self.notification_service.notify_user_async(user_id, title, message):
                    delivered_count += 1
            except Exception as notify_err:
                logger.warning(
                    "Ошибка уведомления инициатора %s: %s", user_id, notify_err
                )

        logger.info(
            "Обработано истёкших передач: %s (scheduled: %s, delivered: %s, ошибок: %s)",
            processed_count,
            scheduled_count,
            delivered_count,
            errors,
        )
        return _result()
