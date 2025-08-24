from sqlalchemy.orm import Session
from sqlalchemy import and_, desc
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta

from uk_management_bot.database.models.shift import Shift
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.audit import AuditLog
from uk_management_bot.utils.constants import (
    SHIFT_STATUS_ACTIVE,
    SHIFT_STATUS_COMPLETED,
    SHIFT_STATUS_CANCELLED,
    ROLE_EXECUTOR,
    ROLE_MANAGER,
    AUDIT_ACTION_SHIFT_STARTED,
    AUDIT_ACTION_SHIFT_ENDED,
)
from uk_management_bot.services.notification_service import notify_shift_started, notify_shift_ended
import logging


logger = logging.getLogger(__name__)


class ShiftService:
    """Сервис для работы со сменами."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def is_user_in_active_shift(self, telegram_id: int) -> bool:
        """Проверяет, находится ли пользователь (исполнитель) в активной смене."""
        try:
            user: Optional[User] = self.db.query(User).filter(User.telegram_id == telegram_id).first()
            if not user:
                logger.warning(f"Пользователь с telegram_id={telegram_id} не найден при проверке смены")
                return False
            exists = (
                self.db.query(Shift)
                .filter(and_(Shift.user_id == user.id, Shift.status == SHIFT_STATUS_ACTIVE))
                .first()
                is not None
            )
            return exists
        except Exception as e:
            logger.error(f"Ошибка при проверке активной смены пользователя {telegram_id}: {e}")
            return False

    def _get_user_by_tg(self, telegram_id: int) -> Optional[User]:
        try:
            return self.db.query(User).filter(User.telegram_id == telegram_id).first()
        except Exception as e:
            logger.error(f"Ошибка получения пользователя по telegram_id={telegram_id}: {e}")
            return None

    def get_active_shift(self, telegram_id: int) -> Optional[Shift]:
        try:
            user = self._get_user_by_tg(telegram_id)
            if not user:
                return None
            return (
                self.db.query(Shift)
                .filter(and_(Shift.user_id == user.id, Shift.status == SHIFT_STATUS_ACTIVE))
                .first()
            )
        except Exception as e:
            logger.error(f"Ошибка получения активной смены для {telegram_id}: {e}")
            return None

    def start_shift(self, telegram_id: int, notes: Optional[str] = None) -> Dict[str, Any]:
        try:
            user = self._get_user_by_tg(telegram_id)
            if not user:
                return {"success": False, "message": "Пользователь не найден", "shift": None}
            if user.role not in [ROLE_EXECUTOR, ROLE_MANAGER]:
                return {"success": False, "message": "Доступ запрещен", "shift": None}
            if self.is_user_in_active_shift(telegram_id):
                return {"success": False, "message": "У вас уже есть активная смена", "shift": None}

            shift = Shift(
                user_id=user.id,
                start_time=datetime.now(),
                status=SHIFT_STATUS_ACTIVE,
                notes=notes,
            )
            self.db.add(shift)
            self.db.commit()
            self.db.refresh(shift)

            # Аудит и уведомление (best-effort)
            try:
                self.db.add(
                    AuditLog(
                        user_id=user.id,
                        action=AUDIT_ACTION_SHIFT_STARTED,
                        details={"shift_id": shift.id, "notes": notes},
                    )
                )
                self.db.commit()
            except Exception as e:
                self.db.rollback()
                logger.error(f"Ошибка записи аудита старта смены: {e}")
            try:
                notify_shift_started(self.db, user, shift)
            except Exception as e:
                logger.error(f"Ошибка отправки уведомления о старте смены: {e}")

            return {"success": True, "message": "Смена начата", "shift": shift}
        except Exception as e:
            self.db.rollback()
            logger.error(f"Ошибка старта смены для {telegram_id}: {e}")
            return {"success": False, "message": "Ошибка при старте смены", "shift": None}

    def end_shift(self, telegram_id: int, notes: Optional[str] = None) -> Dict[str, Any]:
        try:
            user = self._get_user_by_tg(telegram_id)
            if not user:
                return {"success": False, "message": "Пользователь не найден", "shift": None}
            active = self.get_active_shift(telegram_id)
            if not active:
                return {"success": False, "message": "Нет активной смены", "shift": None}

            active.end_time = datetime.now()
            active.status = SHIFT_STATUS_COMPLETED
            if notes:
                active.notes = (active.notes or "") + (f"\n{notes}" if active.notes else notes)
            self.db.commit()
            self.db.refresh(active)

            # Аудит и уведомление
            try:
                self.db.add(
                    AuditLog(
                        user_id=user.id,
                        action=AUDIT_ACTION_SHIFT_ENDED,
                        details={"shift_id": active.id, "notes": notes},
                    )
                )
                self.db.commit()
            except Exception as e:
                self.db.rollback()
                logger.error(f"Ошибка записи аудита завершения смены: {e}")
            try:
                notify_shift_ended(self.db, user, active)
            except Exception as e:
                logger.error(f"Ошибка отправки уведомления о завершении смены: {e}")

            return {"success": True, "message": "Смена завершена", "shift": active}
        except Exception as e:
            self.db.rollback()
            logger.error(f"Ошибка завершения смены для {telegram_id}: {e}")
            return {"success": False, "message": "Ошибка при завершении смены", "shift": None}

    def force_end_shift(
        self,
        manager_telegram_id: int,
        target_user_telegram_id: int,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        try:
            manager = self._get_user_by_tg(manager_telegram_id)
            if not manager or manager.role != ROLE_MANAGER:
                return {"success": False, "message": "Требуются права менеджера", "shift": None}
            active = self.get_active_shift(target_user_telegram_id)
            if not active:
                return {"success": False, "message": "У пользователя нет активной смены", "shift": None}

            active.end_time = datetime.now()
            active.status = SHIFT_STATUS_COMPLETED
            if notes:
                active.notes = (active.notes or "") + (f"\n{notes}" if active.notes else notes)
            self.db.commit()
            self.db.refresh(active)

            try:
                self.db.add(
                    AuditLog(
                        user_id=manager.id,
                        action=AUDIT_ACTION_SHIFT_ENDED,
                        details={"shift_id": active.id, "forced": True, "notes": notes},
                    )
                )
                self.db.commit()
            except Exception as e:
                self.db.rollback()
                logger.error(f"Ошибка аудита force-end смены: {e}")
            try:
                notify_shift_ended(self.db, manager, active)
            except Exception as e:
                logger.error(f"Ошибка уведомления force-end: {e}")

            return {"success": True, "message": "Смена завершена менеджером", "shift": active}
        except Exception as e:
            self.db.rollback()
            logger.error(f"Ошибка force_end_shift: {e}")
            return {"success": False, "message": "Ошибка при завершении смены", "shift": None}

    def list_shifts(
        self,
        telegram_id: Optional[int] = None,
        period: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Shift]:
        try:
            query = self.db.query(Shift)
            if telegram_id:
                user = self._get_user_by_tg(telegram_id)
                if not user:
                    return []
                query = query.filter(Shift.user_id == user.id)
            if status:
                query = query.filter(Shift.status == status)
            if period and period != "all":
                now = datetime.now()
                if period == "today":
                    start = datetime(now.year, now.month, now.day)
                elif period == "7d":
                    start = now - timedelta(days=7)
                elif period == "30d":
                    start = now - timedelta(days=30)
                elif period == "90d":
                    start = now - timedelta(days=90)
                else:
                    start = None
                if start:
                    query = query.filter(Shift.start_time >= start)
            return query.order_by(desc(Shift.start_time)).offset(offset).limit(limit).all()
        except Exception as e:
            logger.error(f"Ошибка выборки смен: {e}")
            return []

    def get_shift_stats(self, telegram_id: Optional[int] = None, period: Optional[str] = None) -> Dict[str, Any]:
        try:
            shifts = self.list_shifts(telegram_id=telegram_id, period=period, status=None, limit=10000, offset=0)
            total_shifts = len(shifts)
            active_count = len([s for s in shifts if s.status == SHIFT_STATUS_ACTIVE])
            total_seconds = 0
            now = datetime.now()
            for s in shifts:
                end = s.end_time or now
                total_seconds += max(0, int((end - s.start_time).total_seconds()))
            total_hours = round(total_seconds / 3600, 2)
            return {"total_shifts": total_shifts, "active_count": active_count, "total_hours": total_hours}
        except Exception as e:
            logger.error(f"Ошибка статистики смен: {e}")
            return {"total_shifts": 0, "active_count": 0, "total_hours": 0.0}


