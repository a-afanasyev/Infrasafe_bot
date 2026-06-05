"""Idempotent backfill: legacy-рус значения requests.urgency → канон-ключи (TASK 17).

Переиспользуется alembic-миграцией 015 и тестом. Источник истины маппинга —
``URGENCY_RU_TO_KEY`` из constants. Значения захардкожены константами (не
пользовательский ввод) → безопасны для inline CASE.

Гейты:
- preflight: до UPDATE проверяем распределение; если есть значение вне 8
  допустимых (4 ключа + 4 legacy-рус) ИЛИ NULL — abort с полным GROUP BY.
- postflight: после UPDATE не осталось неканонических значений (NULL-aware).
"""
import sqlalchemy as sa

from uk_management_bot.utils.constants import URGENCY_VALUES, URGENCY_RU_TO_KEY

_ALLOWED = list(URGENCY_VALUES) + list(URGENCY_RU_TO_KEY)  # 4 ключа + 4 legacy-рус

_CASE = " ".join(f"WHEN '{ru}' THEN '{key}'" for ru, key in URGENCY_RU_TO_KEY.items())
_RU_LIST = ", ".join(f"'{ru}'" for ru in URGENCY_RU_TO_KEY)
_KEY_LIST = ", ".join(f"'{k}'" for k in URGENCY_VALUES)
_ALLOWED_LIST = ", ".join(f"'{v}'" for v in _ALLOWED)

_BACKFILL_SQL = sa.text(
    f"UPDATE requests SET urgency = CASE urgency {_CASE} ELSE urgency END "
    f"WHERE urgency IN ({_RU_LIST})"
)
# NULL-aware: NULL NOT IN (...) → UNKNOWN, поэтому NULL добавляем явно.
_PREFLIGHT_SQL = sa.text(
    f"SELECT urgency, count(*) FROM requests "
    f"WHERE urgency IS NULL OR urgency NOT IN ({_ALLOWED_LIST}) "
    f"GROUP BY urgency"
)
_POSTFLIGHT_SQL = sa.text(
    f"SELECT urgency, count(*) FROM requests "
    f"WHERE urgency IS NULL OR urgency NOT IN ({_KEY_LIST}) "
    f"GROUP BY urgency"
)


def backfill_urgency_to_keys(conn) -> None:
    """Конвертирует рус→ключ; идемпотентно (повторный запуск — no-op).

    preflight (до UPDATE): любое значение вне 8 допустимых или NULL → RuntimeError
    с полным распределением (fail-loud, ничего не меняем).
    postflight (после UPDATE): не осталось неканонических значений или NULL.
    """
    pre = conn.execute(_PREFLIGHT_SQL).fetchall()
    if pre:
        dist = {("NULL" if r[0] is None else r[0]): r[1] for r in pre}
        raise RuntimeError(
            f"urgency backfill preflight: недопустимые значения (исправьте вручную): {dist}"
        )
    conn.execute(_BACKFILL_SQL)
    post = conn.execute(_POSTFLIGHT_SQL).fetchall()
    if post:
        dist = {("NULL" if r[0] is None else r[0]): r[1] for r in post}
        raise RuntimeError(
            f"urgency backfill postflight: неканонические значения остались: {dist}"
        )
