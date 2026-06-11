"""SSOT-кластер #1 cutover (PR3): backfill legacy-кодировки статуса → канон.

Модель A: статус — единственная истина. До cutover canonical-writer кодировал
канон-состояния в legacy-форму хранилища:
  - возврат заявителем  → status="Исполнено" + is_returned=True;
  - подтверждение менеджером (старый бот) → status="Выполнена" + manager_confirmed.

Эта data-миграция приводит хранилище к канону:
  1. Исполнено + is_returned=True  → «Возвращена» (is_returned ОСТАЁТСЯ как
     исторический флаг — defense-in-depth для любого пропущенного legacy-чтения);
  2. Выполнена + manager_confirmed=True И НЕ is_returned → «Исполнено».

Идемпотентна (повторный запуск — no-op) и self-verifying: после конвертации
postflight-гейт падает, если осталась хоть одна legacy-композитная строка.

Логика — здесь (общая с миграцией 019 и тестом), raw SQL (sa.text) как в
015/downgrade: AST write-гейт строковый SQL не видит, отдельная allowlist-
запись не нужна.
"""
from __future__ import annotations

import sqlalchemy as sa

from uk_management_bot.utils.constants import (
    REQUEST_STATUS_COMPLETED,
    REQUEST_STATUS_EXECUTED,
    REQUEST_STATUS_RETURNED,
)


def backfill_returned_status(conn: sa.engine.Connection) -> dict[str, int]:
    """Привести legacy-кодировку статуса к канону. Идемпотентна.

    → {"to_returned": N, "to_completed": M} — сколько строк сконвертировано.
    raise RuntimeError, если postflight-инвариант нарушен.
    """
    # 1. Исполнено + is_returned=True → Возвращена (is_returned сохраняем).
    to_returned = conn.execute(
        sa.text(
            "UPDATE requests SET status = :ret "
            "WHERE status = :done AND is_returned = TRUE"
        ),
        {"ret": REQUEST_STATUS_RETURNED, "done": REQUEST_STATUS_COMPLETED},
    ).rowcount

    # 2. Выполнена + manager_confirmed=True И НЕ возвращена → Исполнено.
    to_completed = conn.execute(
        sa.text(
            "UPDATE requests SET status = :done "
            "WHERE status = :exec AND manager_confirmed = TRUE "
            "AND is_returned = FALSE"
        ),
        {"done": REQUEST_STATUS_COMPLETED, "exec": REQUEST_STATUS_EXECUTED},
    ).rowcount

    # Postflight: legacy-композитных строк не осталось.
    left_returned = conn.execute(
        sa.text(
            "SELECT count(*) FROM requests "
            "WHERE status = :done AND is_returned = TRUE"
        ),
        {"done": REQUEST_STATUS_COMPLETED},
    ).scalar()
    left_confirmed = conn.execute(
        sa.text(
            "SELECT count(*) FROM requests "
            "WHERE status = :exec AND manager_confirmed = TRUE "
            "AND is_returned = FALSE"
        ),
        {"exec": REQUEST_STATUS_EXECUTED},
    ).scalar()
    if left_returned or left_confirmed:
        raise RuntimeError(
            "returned_status_backfill postflight failed: "
            f"Исполнено+is_returned={left_returned}, "
            f"Выполнена+manager_confirmed={left_confirmed}"
        )

    return {"to_returned": to_returned, "to_completed": to_completed}


def revert_returned_status(conn: sa.engine.Connection) -> int:
    """Откат чистой части: Возвращена → Исполнено (строки несут is_returned=True,
    под старым dual-read нормализуются обратно в «Возвращена»). Идемпотентна.

    Конверсия #2 (Исполнено←Выполнена) НЕ откатывается — она необратима
    (нельзя отличить исходный «Исполнено» от сконвертированного), но и не
    регрессирует: старый dual-read читает Исполнено+manager_confirmed как
    «Исполнено». Поэтому миграция помечена one-way по этой части.
    """
    return conn.execute(
        sa.text(
            "UPDATE requests SET status = :done WHERE status = :ret"
        ),
        {"done": REQUEST_STATUS_COMPLETED, "ret": REQUEST_STATUS_RETURNED},
    ).rowcount
