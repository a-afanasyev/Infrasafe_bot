"""Общие типы и миксины доменного слоя access_control (Ф2).

Здесь — портабельные между PostgreSQL и sqlite (CI/dev) определения типов и
hash-chain миксин append-only таблиц (§9.7). Все пилотные модели регистрируются
на общем ``Base`` из ``uk_management_bot.database.session`` — том же declarative
Base, что использует alembic env.py и тестовый ``create_all``.

Конвенция типов (DATA_MODEL_PILOT):
* новые PK — ``BIGINT`` (``BigIntPK``: на sqlite сводится к INTEGER ради
  autoincrement rowid);
* FK на ``users``/``yards``/``apartments`` — ``INTEGER`` (их фактический PK);
* метки времени — ``TIMESTAMPTZ`` (``DateTime(timezone=True)``);
* гибкие атрибуты — ``JSONB`` на pg, ``JSON`` на sqlite (``JSONB_PORTABLE``);
* ``command_id``/``lease_token``/``decision_group_id`` — ``UUID``
  (``sqlalchemy.Uuid``: нативный uuid на pg, CHAR(32) на sqlite).
"""
from __future__ import annotations

from sqlalchemy import BigInteger, Column, DateTime, Integer, JSON, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

# Re-export Uuid из SQLAlchemy 2.0 — кросс-диалектный (native uuid / CHAR(32)).
from sqlalchemy import Uuid  # noqa: F401  (re-export для доменных моделей)

# BIGINT PK с autoincrement; на sqlite — INTEGER, иначе rowid-autoincrement
# не работает (sqlite инкрементит только INTEGER PRIMARY KEY).
BigIntPK = BigInteger().with_variant(Integer, "sqlite")

# JSONB на postgres, JSON на sqlite — единый тип для гибких атрибутов.
JSONB_PORTABLE = JSON().with_variant(JSONB(), "postgresql")


def pk_column() -> Column:
    """Стандартный BIGINT-PK пилотных таблиц."""
    return Column(BigIntPK, primary_key=True, autoincrement=True)


def created_at_column() -> Column:
    """TIMESTAMPTZ created_at со server_default now()."""
    return Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


def updated_at_column() -> Column:
    """TIMESTAMPTZ updated_at (onupdate now())."""
    return Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)


class HashChainMixin:
    """Колонки hash-chain для append-only таблиц (§9.7, решение CTO #9).

    Сама генерация ``row_hash = sha256(prev_hash ‖ canonical_json(row))`` — в
    сервисном слое (Ф3+). На Ф2 объявляются только колонки. ``per-table`` цепочка.
    """

    # sha256 hex = 64 символа; nullable — первая запись/до вычисления в сервисе.
    prev_hash = Column(String(64), nullable=True)
    row_hash = Column(String(64), nullable=True)
