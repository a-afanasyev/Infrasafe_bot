"""Мутации раздела «Жители» — владелец транзакции (PR-3).

Форма КАЖДОЙ операции одна и та же и менять её нельзя:

    валидация → мутация (+ вложенные вызовы с commit=False)
              → AuditLog
              → enqueue_outbox (ТОЛЬКО если event не None)
              → ЕДИНСТВЕННЫЙ commit
              → publish_realtime_after_commit
              → TG-уведомление (best-effort, никогда не роняет запрос)

Порядок не косметический:
  * `enqueue_outbox` пишет строку в ТУ ЖЕ транзакцию — если после неё упадёт
    AuditLog, откатится и событие; иначе получили бы событие о том, чего не
    произошло;
  * `publish_realtime_after_commit` — строго ПОСЛЕ commit: подписчик Redis
    получает уведомление и тут же читает БД, а до коммита прочитал бы старое;
  * уведомление в Telegram — последним и в try/except: внешний сервис не имеет
    права откатывать уже зафиксированное решение менеджера.

Чужие мутации (`addresses/core.py`, `shifts/service.py`) зовутся с
`commit=False` — см. контракт в tests/api/test_residents_commit_contract.py.
"""

import json
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.api.shifts import service as shifts_service
from uk_management_bot.database.models.apartment import Apartment
from uk_management_bot.database.models.audit import AuditLog
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.user_apartment import (
    UserApartment, UserApartmentStatus,
)
from uk_management_bot.services.addresses import core as addresses_core
from uk_management_bot.services.addresses.events import (
    enqueue_outbox, publish_realtime_after_commit,
)
from uk_management_bot.services.addresses.payloads import build_apartment_event_data
from uk_management_bot.services.residents import queries
from uk_management_bot.services.residents.exceptions import (
    ResidentConflict, ResidentNotFound, ResidentValidationError,
)
from uk_management_bot.utils.auth_helpers import parse_roles_safe

logger = logging.getLogger(__name__)

# Роли, при которых блокировка из раздела «Жители» безопасна (Т2).
# `resource_meter_entry` — капабилити, а не рабочая роль: контролёр показаний
# остаётся жителем, и его блокировка не отнимает ничьих рабочих доступов.
PURE_APPLICANT_ROLES = frozenset({"applicant", "resource_meter_entry"})


# ───────────────────────── общие помощники ─────────────────────────

async def _require_resident(db: AsyncSession, resident_id: int) -> User:
    resident = await queries.get_resident(db, resident_id)
    if resident is None:
        raise ResidentNotFound("Житель не найден")
    return resident


async def _lock_and_require_resident(db: AsyncSession, resident_id: int) -> User:
    """Лок строки жителя + ПЕРЕЧИТКА — именно в таком порядке.

    Guard'ы статуса (approve/block/unblock) обязаны видеть состояние на момент
    ПОСЛЕ лока. `db.get()` этого не даёт: при уже загруженном объекте он
    отдаёт его из identity map вообще без SQL, и повторный approve прошёл бы
    вторым. Подробности — в докстринге `_require_binding`.
    """
    await _lock_resident(db, resident_id)
    resident = (await db.execute(
        select(User)
        .where(User.id == resident_id, *queries._resident_scope())
        .execution_options(populate_existing=True)
    )).scalar_one_or_none()
    if resident is None:
        raise ResidentNotFound("Житель не найден")
    return resident


async def _require_binding(db: AsyncSession, resident_id: int, ua_id: int) -> UserApartment:
    """Привязка ИМЕННО этого жителя (Т3), перечитанная из БД.

    Чужой `ua_id` — 404, а не 403: раскрывать существование чужой привязки
    незачем, а перепутанный id в URL выглядит одинаково в обоих случаях.

    ⚠ `populate_existing=True`, а не `db.get()`. Зовётся эта функция ПОСЛЕ
    взятия лока, и весь смысл — увидеть состояние на момент после лока. Но
    `db.get()` при уже загруженном объекте отдаёт его из identity map вообще
    без SQL, поэтому guard'ы («заявка уже обработана», «последняя основная»)
    сверялись бы с состоянием ДО лока. Проверено на живом PostgreSQL:
    db.get() → 'pending', populate_existing → 'approved'.
    """
    ua = (await db.execute(
        select(UserApartment)
        .where(UserApartment.id == ua_id)
        .execution_options(populate_existing=True)
    )).scalar_one_or_none()
    if ua is None or ua.user_id != resident_id:
        raise ResidentNotFound("Привязка не найдена")
    return ua


def _ensure_pure_applicant(resident: User) -> None:
    """Т2: блокировать из раздела «Жители» можно только «чистого» жителя.

    `users.status` общий на ВСЕ роли: заблокировав жителя, который ещё и
    исполнитель, мы отнимем у него рабочий доступ. Такие аккаунты блокируются
    из раздела «Сотрудники», где у операции свой guard и свой контекст.

    Тот же guard стоит и на одобрении: «Сотрудники» активируют через
    `activate_employee`, который кроме `status` поднимает `active_role` до
    стафф-роли, — здешний путь сделал бы только половину. Поэтому текст ошибки
    нейтрален к операции: он общий для approve, block и unblock.
    """
    roles = set(parse_roles_safe(resident.roles))
    staff = roles - PURE_APPLICANT_ROLES
    if staff:
        raise ResidentConflict(
            "У пользователя есть роли персонала "
            f"({', '.join(sorted(staff))}) — управляйте его аккаунтом "
            "из раздела «Сотрудники»",
            code="has_staff_roles",
        )


def _audit(db: AsyncSession, *, action: str, actor_id: int, resident: User, details: dict) -> None:
    """AuditLog теми же литералами действий, что и бот (`auth_service.py`)."""
    db.add(AuditLog(
        action=action,
        user_id=actor_id,
        telegram_user_id=resident.telegram_id,
        details=json.dumps({"target_user_id": resident.id, **details}, ensure_ascii=False),
    ))


async def _finish(db: AsyncSession, *, event: str | None, payload: dict | None) -> None:
    """Единственный commit операции + пост-коммитная публикация.

    `event=None` — легальный случай (у статусов аккаунта событий нет);
    `enqueue_outbox` при этом НЕ зовётся: он падает ValueError на неизвестном
    событии, и это правильно — молча терять события нельзя.
    """
    if event is not None:
        await enqueue_outbox(db, event=event, data=payload or {})
    await db.commit()
    if event is not None:
        await publish_realtime_after_commit(event, payload or {})


# ───────────────────────── инвариант основной квартиры ─────────────────────────

async def _lock_resident(db: AsyncSession, resident_id: int) -> None:
    """Сериализация изменений состава привязок жителя (Т6).

    Блокируется строка `users`, а НЕ строки связей: при первом конкурентном
    attach блокировать в `user_apartments` ещё нечего, и оба запроса создали бы
    по primary. На sqlite `FOR UPDATE` не поддерживается и молча не нужен —
    там нет конкуренции.
    """
    if not queries._is_postgres(db):
        return
    await db.execute(
        select(User.id).where(User.id == resident_id).with_for_update()
    )


async def _ensure_single_primary(
    db: AsyncSession, resident_id: int, *, keep_ua_id: int | None,
    exclude_ua_id: int | None = None,
) -> None:
    """Инвариант: не более одной primary; при наличии approved — ровно одна.

    Зовётся на ВСЕХ путях, меняющих состав или статус привязок, — иначе
    инвариант держится «почти всегда», что хуже, чем не держится вовсе.

    `keep_ua_id` — привязка, которая обязана стать primary (None = выбрать
    самую старую approved).

    `exclude_ua_id` — привязка, которой основной становиться ЗАПРЕЩЕНО.
    Нужна ровно на одном пути: менеджер снимает признак основной. Без неё
    «самой старой approved» оказывалась та же самая привязка, у которой
    признак только что сняли, и запрос молча возвращал состояние как было —
    с ответом 200. Найдено прод-проверкой на profk: снятие признака у первой
    (самой старой) квартиры не давало никакого эффекта.
    """
    approved = list((await db.execute(
        select(UserApartment)
        .where(
            UserApartment.user_id == resident_id,
            UserApartment.status == UserApartmentStatus.APPROVED.value,
        )
        .order_by(UserApartment.requested_at.asc(), UserApartment.id.asc())
        .execution_options(populate_existing=True)
    )).scalars().all())
    candidates = [ua for ua in approved if ua.id != exclude_ua_id]

    if not candidates:
        # approved-привязок не осталось — снимаем флаг со всех прочих, чтобы
        # pending/rejected не унесли с собой висячую primary.
        for ua in await _all_bindings(db, resident_id):
            ua.is_primary = False
        return

    winner = None
    if keep_ua_id is not None:
        winner = next((ua for ua in candidates if ua.id == keep_ua_id), None)
    if winner is None:
        winner = next((ua for ua in candidates if ua.is_primary), candidates[0])

    for ua in await _all_bindings(db, resident_id):
        ua.is_primary = (ua.id == winner.id)
    await db.flush()


async def _all_bindings(db: AsyncSession, resident_id: int) -> list[UserApartment]:
    return list((await db.execute(
        select(UserApartment)
        .where(UserApartment.user_id == resident_id)
        .execution_options(populate_existing=True)
    )).scalars().all())


# ───────────────────────── аккаунт ─────────────────────────

async def approve_account(
    db: AsyncSession, *, resident_id: int, actor_id: int, comment: str | None = None,
) -> User:
    """`pending → approved`. Повторный approve и approve заблокированного — 409 (Т13).

    Стафф отсюда не одобряется (Т2). «Сотрудники» активируют через
    `shifts_service.activate_employee`, который кроме `status` поднимает
    `active_role` до стафф-роли и подтягивает `verification_status`; здешний
    путь делает только первое. Приглашённый через бота сотрудник после `/join`
    остаётся `applicant` + стафф-роль в статусе `pending`, то есть попадает в
    список жителей, — и одобрение отсюда оставило бы его без меню в боте, ровно
    как описано в докстринге `activate_employee`.
    """
    resident = await _lock_and_require_resident(db, resident_id)
    # До проверки статуса: иначе стафф видел бы «уже одобрен» и не понимал, что
    # раздел вообще не его.
    _ensure_pure_applicant(resident)
    if resident.status == "approved":
        raise ResidentConflict("Аккаунт уже одобрен", code="already_approved")
    if resident.status != "pending":
        raise ResidentConflict(
            f"Одобрить можно только аккаунт в статусе «ожидает» (сейчас: {resident.status})",
            code="not_pending",
        )

    old_status = resident.status
    result = await shifts_service.set_user_status(db, resident, "approved", commit=False)
    _audit(db, action="user_approved", actor_id=actor_id, resident=resident,
           details={"old_status": old_status, "new_status": "approved", "comment": comment})
    await _finish(db, event=result["event"], payload=result["payload"])
    logger.info("Житель %s одобрен менеджером %s", resident_id, actor_id)
    return resident


async def block_account(
    db: AsyncSession, *, resident_id: int, actor_id: int, reason: str,
) -> User:
    """`pending|approved → blocked`. Только «чистый» житель (Т2)."""
    reason = (reason or "").strip()
    if len(reason) < 3:
        raise ResidentValidationError("Причина блокировки — минимум 3 символа")

    resident = await _lock_and_require_resident(db, resident_id)
    _ensure_pure_applicant(resident)
    if resident.status == "blocked":
        raise ResidentConflict("Аккаунт уже заблокирован", code="already_blocked")

    old_status = resident.status
    result = await shifts_service.set_user_status(db, resident, "blocked", commit=False)
    _audit(db, action="user_blocked", actor_id=actor_id, resident=resident,
           details={"old_status": old_status, "new_status": "blocked", "reason": reason})
    await _finish(db, event=result["event"], payload=result["payload"])
    logger.info("Житель %s заблокирован менеджером %s", resident_id, actor_id)
    return resident


async def unblock_account(db: AsyncSession, *, resident_id: int, actor_id: int) -> User:
    """`blocked → approved`. Из любого другого статуса — 409 (Т13)."""
    resident = await _lock_and_require_resident(db, resident_id)
    _ensure_pure_applicant(resident)
    if resident.status != "blocked":
        raise ResidentConflict(
            f"Аккаунт не заблокирован (статус: {resident.status})", code="not_blocked",
        )

    result = await shifts_service.set_user_status(db, resident, "approved", commit=False)
    _audit(db, action="user_unblocked", actor_id=actor_id, resident=resident,
           details={"old_status": "blocked", "new_status": "approved"})
    await _finish(db, event=result["event"], payload=result["payload"])
    logger.info("Житель %s разблокирован менеджером %s", resident_id, actor_id)
    return resident


# ───────────────────────── привязки к квартирам ─────────────────────────

async def attach_apartment(
    db: AsyncSession,
    *,
    resident_id: int,
    apartment_id: int,
    actor_id: int,
    is_owner: bool = False,
    is_primary: bool = False,
) -> UserApartment:
    """Привязка менеджером — сразу `approved` (решение владельца).

    Менеджер и есть модерация: заводить его же заявку в очередь на самого себя
    бессмысленно. Флаг `is_primary` от клиента ИГНОРИРУЕТСЯ в пользу инварианта
    (Т6), когда approved-привязка первая: она становится основной независимо от
    запроса.
    """
    resident = await _require_resident(db, resident_id)
    await _lock_resident(db, resident_id)

    apartment = await db.get(Apartment, apartment_id)
    if apartment is None:
        raise ResidentNotFound("Квартира не найдена")
    if not apartment.is_active:
        raise ResidentConflict("Квартира неактивна", code="apartment_inactive")

    existing_binding = (await db.execute(
        select(UserApartment).where(
            UserApartment.user_id == resident_id,
            UserApartment.apartment_id == apartment_id,
        ).execution_options(populate_existing=True)
    )).scalar_one_or_none()
    if existing_binding is not None:
        if existing_binding.status != UserApartmentStatus.REJECTED.value:
            raise ResidentConflict(
                f"Связь с этой квартирой уже есть (статус: {existing_binding.status})",
                code="binding_exists",
            )
        # Ранее отклонённая заявка — не приговор: менеджер вправе передумать, а
        # другого пути исправить свой же отказ у него нет (uix_user_apartment
        # запрещает вторую строку на ту же пару). Переиспользуем строку.
        existing_binding.status = UserApartmentStatus.APPROVED.value
        existing_binding.is_owner = is_owner
        existing_binding.reviewed_by = actor_id
        existing_binding.admin_comment = None
        await db.flush()
        await _ensure_single_primary(
            db, resident_id, keep_ua_id=existing_binding.id if is_primary else None,
        )
        payload = build_apartment_event_data(apartment)
        _audit(db, action="resident_apartment_attached", actor_id=actor_id,
               resident=resident,
               details={"apartment_id": apartment_id, "user_apartment_id": existing_binding.id,
                        "is_owner": is_owner, "reopened_from": "rejected"})
        await _finish(db, event="apartment_request.approved", payload=payload)
        logger.info("Житель %s повторно привязан к квартире %s (был отказ) менеджером %s",
                    resident_id, apartment_id, actor_id)
        return existing_binding

    ua = UserApartment(
        user_id=resident_id,
        apartment_id=apartment_id,
        status=UserApartmentStatus.APPROVED.value,
        is_owner=is_owner,
        is_primary=False,          # решит _ensure_single_primary
        reviewed_by=actor_id,
    )
    db.add(ua)
    await db.flush()
    await _ensure_single_primary(db, resident_id, keep_ua_id=ua.id if is_primary else None)

    payload = build_apartment_event_data(apartment)
    _audit(db, action="resident_apartment_attached", actor_id=actor_id, resident=resident,
           details={"apartment_id": apartment_id, "user_apartment_id": ua.id,
                    "is_owner": is_owner})
    await _finish(db, event="apartment_request.approved", payload=payload)
    logger.info("Житель %s привязан к квартире %s менеджером %s",
                resident_id, apartment_id, actor_id)
    return ua


async def approve_binding(
    db: AsyncSession, *, resident_id: int, ua_id: int, actor_id: int,
    comment: str | None = None,
) -> UserApartment:
    """Подтвердить заявку жителя на привязку (очередь модерации)."""
    # Порядок обязателен: лок → перечитка → guard. Наоборот — guard увидит
    # состояние до лока (см. докстринг `_require_binding`).
    resident = await _require_resident(db, resident_id)
    await _lock_resident(db, resident_id)
    await _require_binding(db, resident_id, ua_id)

    result = await addresses_core.approve_apartment_request(
        db, user_apartment_id=ua_id, reviewer_id=actor_id, comment=comment, commit=False,
    )
    # Первая approved-привязка становится основной; если primary уже есть —
    # новая её не отнимает.
    await _ensure_single_primary(db, resident_id, keep_ua_id=None)

    _audit(db, action="resident_binding_approved", actor_id=actor_id, resident=resident,
           details={"user_apartment_id": ua_id, "comment": comment})
    await _finish(db, event=result["event"], payload=result["payload"])
    return result["entity"]


async def reject_binding(
    db: AsyncSession, *, resident_id: int, ua_id: int, actor_id: int, comment: str,
) -> UserApartment:
    """Отклонить заявку на привязку. Комментарий обязателен — житель увидит причину."""
    comment = (comment or "").strip()
    if len(comment) < 3:
        raise ResidentValidationError("Комментарий к отказу — минимум 3 символа")

    resident = await _require_resident(db, resident_id)
    await _lock_resident(db, resident_id)
    await _require_binding(db, resident_id, ua_id)

    result = await addresses_core.reject_apartment_request(
        db, user_apartment_id=ua_id, reviewer_id=actor_id, comment=comment, commit=False,
    )
    # Отклонённая привязка не может остаться основной.
    await _ensure_single_primary(db, resident_id, keep_ua_id=None)

    _audit(db, action="resident_binding_rejected", actor_id=actor_id, resident=resident,
           details={"user_apartment_id": ua_id, "comment": comment})
    await _finish(db, event=result["event"], payload=result["payload"])
    return result["entity"]


async def update_binding(
    db: AsyncSession, *, resident_id: int, ua_id: int, actor_id: int,
    is_owner: bool | None = None, is_primary: bool | None = None,
) -> UserApartment:
    """Сменить роль в квартире (владелец/жилец) и/или назначить основной.

    `is_primary=false` у текущей основной — 409, если других approved нет:
    снять единственную основную нельзя, иначе у жителя с квартирой не остаётся
    адреса по умолчанию. Если другие есть — основной становится самая старая.
    """
    resident = await _require_resident(db, resident_id)
    await _lock_resident(db, resident_id)
    ua = await _require_binding(db, resident_id, ua_id)

    if is_owner is not None:
        ua.is_owner = is_owner

    if is_primary is True:
        if ua.status != UserApartmentStatus.APPROVED.value:
            raise ResidentConflict(
                "Основной можно сделать только подтверждённую квартиру",
                code="primary_requires_approved",
            )
        await db.flush()
        await _ensure_single_primary(db, resident_id, keep_ua_id=ua_id)
    elif is_primary is False:
        others = [
            b for b in await _all_bindings(db, resident_id)
            if b.id != ua_id and b.status == UserApartmentStatus.APPROVED.value
        ]
        if ua.is_primary and not others:
            raise ResidentConflict(
                "Нельзя снять признак основной у единственной подтверждённой квартиры",
                code="last_primary",
            )
        ua.is_primary = False
        await db.flush()
        # exclude: иначе «самой старой approved» окажется она же, и снятие
        # признака не даст никакого эффекта при ответе 200.
        await _ensure_single_primary(db, resident_id, keep_ua_id=None,
                                     exclude_ua_id=ua_id)
    else:
        await db.flush()

    _audit(db, action="resident_binding_updated", actor_id=actor_id, resident=resident,
           details={"user_apartment_id": ua_id, "is_owner": is_owner, "is_primary": is_primary})

    apartment = await db.get(Apartment, ua.apartment_id)
    payload = build_apartment_event_data(apartment) if apartment else {"id": ua.apartment_id}
    await _finish(db, event="apartment_request.approved", payload=payload)
    return ua


async def remove_binding(
    db: AsyncSession, *, resident_id: int, ua_id: int, actor_id: int,
) -> None:
    """Отвязать квартиру. Основная — promote самой старой из оставшихся approved."""
    resident = await _require_resident(db, resident_id)
    await _lock_resident(db, resident_id)
    ua = await _require_binding(db, resident_id, ua_id)
    apartment_id = ua.apartment_id

    result = await addresses_core.remove_user_from_apartment(
        db, user_apartment_id=ua_id, commit=False,
    )
    await _ensure_single_primary(db, resident_id, keep_ua_id=None)

    _audit(db, action="resident_binding_removed", actor_id=actor_id, resident=resident,
           details={"user_apartment_id": ua_id, "apartment_id": apartment_id})
    await _finish(db, event=result["event"], payload=result["payload"])
    logger.info("Житель %s отвязан от квартиры %s менеджером %s",
                resident_id, apartment_id, actor_id)
