"""Одноразовые коды гостевых пропусков: генерация, verify + атомарное погашение (§9.3).

Код §9.3:
* 8 цифровых символов из криптостойкого генератора (``secrets``);
* TTL ≤ 30 минут (клампит ``valid_until`` при генерации в ``resident``);
* в БД хранится ТОЛЬКО HMAC-SHA256(код, ``ACCESS_CODE_SECRET``) — не сам код;
* одноразово погашается АТОМАРНОЙ операцией (``UPDATE ... WHERE used<max`` →
  rowcount=1 успех, 0 — уже погашен/гонка);
* не выводится в access/application logs (этот модуль НЕ логирует код);
* оператор видит квартиру и тип ТОЛЬКО после успешной проверки (раскрытие — в
  ``RedeemResult``, который собирается лишь на успехе).

Секрет резолвится из env ``ACCESS_CODE_SECRET`` БЕЗ literal-дефолта (как H2/M1
device-auth): отсутствие env → RuntimeError. Тесты задают синтетический секрет
(``conftest``); прод/стенд — секрет-хранилище.

Погашение идёт под per-barrier advisory lock (§13.2), общим с ingestion/lifecycle:
создаёт durable-команду открытия + manual_opening + audit (без кода).
"""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import logging
import os
import secrets
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

from access_control.repositories import (
    audit_repo,
    barrier_commands_repo,
    equipment_repo,
    manual_openings_repo,
)
from access_control.services.locks import barrier_advisory_lock

logger = logging.getLogger(__name__)

# Длина кода (§9.3): ровно 8 цифровых символов.
CODE_LENGTH = 8
# TTL команды открытия по гостевому коду — согласован с ручным открытием (§9.2).
GUEST_CODE_COMMAND_TTL_SECONDS = 120
# Имя env-секрета HMAC кода. Literal-дефолта нет (§9.3, как H2/M1 device-auth):
# отсутствие env → RuntimeError при первом использовании.
_CODE_SECRET_ENV = "ACCESS_CODE_SECRET"


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _code_secret() -> bytes:
    secret = os.getenv(_CODE_SECRET_ENV)
    if not secret:
        raise RuntimeError(
            f"{_CODE_SECRET_ENV} не задан: literal-дефолт секрета одноразовых кодов "
            "запрещён (§9.3, §11)."
        )
    return secret.encode("utf-8")


# --------------------------- крипто-примитивы (§9.3) ---------------------------


def generate_code() -> str:
    """Криптостойкий 8-значный цифровой код (``secrets``). Ведущие нули допустимы."""
    return "".join(secrets.choice("0123456789") for _ in range(CODE_LENGTH))


def hash_code(code: str) -> str:
    """HMAC-SHA256(код, ACCESS_CODE_SECRET) в hex — единственное, что хранится (§9.3)."""
    return hmac.new(_code_secret(), code.encode("utf-8"), hashlib.sha256).hexdigest()


# --------------------------- исключения / DTO ---------------------------


class CodeRedeemError(Exception):
    """Код невалиден/истёк/погашен/нет barrier — ОБЩАЯ ошибка (§9.3, no enumeration).

    Конкретная причина НЕ раскрывается клиенту (иначе enumeration-канал
    существования кодов/квартир). Детализация — только server-side лог БЕЗ кода.
    """


@dataclass(frozen=True)
class RedeemResult:
    """Результат успешного погашения (раскрытие квартиры/типа ТОЛЬКО при успехе §9.3)."""

    pass_id: int
    apartment_id: int
    pass_type: str
    valid_until: dt.datetime | None
    command_id: str
    barrier_id: int


@dataclass(frozen=True)
class _Candidate:
    pass_id: int
    apartment_id: int
    pass_type: str
    zone_id: int | None
    valid_until: dt.datetime | None
    stored_hash: str


# --------------------------- резолв barrier ---------------------------


def _resolve_barrier(
    db: Session, *, zone_id: int | None, barrier_id: int | None
) -> tuple[int, int] | None:
    """Определить (barrier_id, controller_id) для открытия по коду.

    Явный ``barrier_id`` имеет приоритет (должен быть активен). Иначе — активный
    barrier зоны пропуска (один — берётся; нет — ``None``).
    """
    if barrier_id is not None:
        controller_id = equipment_repo.active_controller_for_barrier(db, barrier_id)
        if controller_id is None:
            return None
        return barrier_id, int(controller_id)
    if zone_id is None:
        return None
    row = db.execute(
        text(
            "SELECT b.id, b.controller_id FROM access_barriers b "
            "JOIN access_gates g ON g.id = b.gate_id "
            "WHERE g.zone_id = :z AND b.is_active = true "
            "ORDER BY b.id LIMIT 1"
        ),
        {"z": zone_id},
    ).first()
    if row is None:
        return None
    return int(row[0]), int(row[1])


def _find_candidate(db: Session, code_hash: str, now: dt.datetime) -> _Candidate | None:
    """Найти активный гостевой пропуск по HMAC-хэшу кода (валидный, не исчерпанный)."""
    row = db.execute(
        text(
            "SELECT id, apartment_id, pass_type, zone_id, valid_until, one_time_code_hash "
            "FROM access_passes "
            "WHERE pass_type = 'guest' AND one_time_code_hash = :h "
            "AND status = 'active' AND valid_until > :now AND used_entries < max_entries"
        ),
        {"h": code_hash, "now": now},
    ).first()
    if row is None:
        return None
    return _Candidate(
        pass_id=int(row[0]),
        apartment_id=int(row[1]),
        pass_type=row[2],
        zone_id=row[3],
        valid_until=row[4],
        stored_hash=row[5],
    )


# --------------------------- публичная операция ---------------------------


def redeem_code(
    db: Session,
    *,
    code: str,
    operator_user_id: int,
    barrier_id: int | None = None,
    ip_address: str | None = None,
    now: dt.datetime | None = None,
) -> RedeemResult:
    """Проверить и атомарно погасить одноразовый код, открыв шлагбаум (§9.3).

    Поток: HMAC(код) → поиск активного guest-пропуска → ``compare_digest`` →
    резолв barrier (тело/зона) → per-barrier advisory lock → АТОМАРНЫЙ
    ``UPDATE used_entries`` (rowcount=1 успех) → durable-команда + manual_opening +
    audit (``access.guest_code_redeemed``, БЕЗ кода). Любая неудача → ``CodeRedeemError``
    (общая, no enumeration) с откатом; раскрытие квартиры/типа — только в результате.
    """
    now = now or _utcnow()
    code_hash = hash_code(code)

    candidate = _find_candidate(db, code_hash, now)
    if candidate is None:
        db.rollback()
        logger.info("guest code redeem rejected: no active matching pass")
        raise CodeRedeemError("invalid or expired code")

    # Постоянное сравнение хэшей (§9.3) — защита даже при равенстве в SQL.
    if not hmac.compare_digest(candidate.stored_hash or "", code_hash):
        db.rollback()
        logger.info("guest code redeem rejected: hash mismatch")
        raise CodeRedeemError("invalid or expired code")

    resolved = _resolve_barrier(
        db, zone_id=candidate.zone_id, barrier_id=barrier_id
    )
    if resolved is None:
        db.rollback()
        logger.info(
            "guest code redeem rejected: no active barrier (pass_id=%s)",
            candidate.pass_id,
        )
        raise CodeRedeemError("invalid or expired code")
    resolved_barrier_id, controller_id = resolved

    # Сериализация по barrier (§13.2), как ingestion/lifecycle.
    barrier_advisory_lock(db, resolved_barrier_id)

    # Атомарное погашение (§9.3): rowcount=1 → успех; 0 → уже погашен/гонка.
    result = db.execute(
        text(
            "UPDATE access_passes "
            "SET used_entries = used_entries + 1, "
            "    status = CASE WHEN used_entries + 1 >= max_entries THEN 'used' "
            "                  ELSE status END, "
            "    updated_at = now() "
            "WHERE id = :id AND status = 'active' AND used_entries < max_entries"
        ),
        {"id": candidate.pass_id},
    )
    if result.rowcount != 1:
        db.rollback()
        logger.info(
            "guest code redeem rejected: already redeemed/race (pass_id=%s)",
            candidate.pass_id,
        )
        raise CodeRedeemError("invalid or expired code")

    # Durable-команда открытия (manual, decision_id=None → независимая команда §9.2).
    command = barrier_commands_repo.create_open_command(
        db,
        controller_id=controller_id,
        barrier_id=resolved_barrier_id,
        decision_id=None,
        ttl_seconds=GUEST_CODE_COMMAND_TTL_SECONDS,
    )
    # Append-only manual_opening: оператор + ссылка на команду; источник — guest_code.
    manual_openings_repo.insert(
        db,
        barrier_id=resolved_barrier_id,
        command_id=command.command_id,
        decision_id=None,
        operator_user_id=operator_user_id,
        reason="guest_code",
        captured_event_id=None,
    )
    # Аудит БЕЗ кода (§9.3/§11): только идентификаторы и тип.
    audit_repo.insert(
        db,
        actor_user_id=operator_user_id,
        action="access.guest_code_redeemed",
        entity_type="access_pass",
        entity_id=candidate.pass_id,
        barrier_id=resolved_barrier_id,
        source="guest_code",
        reason=None,
        ip_address=ip_address,
        extra_details={
            "apartment_id": candidate.apartment_id,
            "pass_type": candidate.pass_type,
        },
    )
    db.commit()
    return RedeemResult(
        pass_id=candidate.pass_id,
        apartment_id=candidate.apartment_id,
        pass_type=candidate.pass_type,
        valid_until=candidate.valid_until,
        command_id=command.command_id,
        barrier_id=resolved_barrier_id,
    )
