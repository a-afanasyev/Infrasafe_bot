"""Гейт окружения: БД-зависимые наборы ДОЛЖНЫ идти на PostgreSQL.

Критерии приёмки 1–4 и 10 (ingestion), а также append-only (§9.7) и hash-chain
проверяются только на postgres (advisory-lock §13.2, ``INSERT ... ON CONFLICT``
§10.1, partial-unique индексы, append-only PL/pgSQL-триггеры). На sqlite эти
наборы тихо ``skip`` — что выглядит «зелёным», но НИЧЕГО не доказывает.

Этот тест делает скрытую подмену явной: если прогон идёт не на postgres — он
ПАДАЕТ (а не skip), сигнализируя, что результаты ingestion/append-only/hash-chain
недействительны. Чистые unit-тесты нормализации (§12) остаются БД-независимыми и
этим гейтом не затрагиваются.
"""
from __future__ import annotations

from uk_management_bot.config.settings import settings


def test_db_dependent_suite_runs_on_postgres() -> None:
    """FAIL (не skip), если БД-зависимый прогон выполняется не на PostgreSQL."""
    assert settings.DATABASE_URL.startswith("postgresql"), (
        "Наборы ingestion (критерии 1–4,10), append-only (§9.7) и hash-chain "
        "обязаны выполняться на PostgreSQL: advisory-lock §13.2, ON CONFLICT §10.1, "
        "partial-unique индексы и append-only триггеры на sqlite не воспроизводятся. "
        f"Текущий DATABASE_URL={settings.DATABASE_URL!r} — зелёный sqlite-прогон НЕ "
        "доказывает эти критерии."
    )
