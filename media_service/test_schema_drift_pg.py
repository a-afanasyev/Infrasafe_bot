"""A9-P2-21: дрейф-гейт схемы uk_media на настоящем PostgreSQL.

У media нет alembic: схему строят `Base.metadata.create_all` (старт сервиса,
создаёт только отсутствующие таблицы) и идемпотентные `migrations/*.sql`
(`run_migrations.py`, шаг media-migrate). Гейт сверяет обе дороги с моделями:

* fresh   — пустая БД: create_all → migrations  == модели;
* upgrade — существующая прод-БД (schema_baseline/pre_0001.sql) →
            migrations → create_all == модели. Это и есть ловушка «колонку
            добавили в модель, а миграцию забыли»: create_all её не добавит.

Эталон «модели» — чистый create_all в отдельной схеме; сравнение идёт
рефлексия-к-рефлексии (колонки/типы/nullability/server default, PK, UNIQUE,
индексы с partial-предикатом, FK), поэтому нормализация типов не нужна.

Запуск: MEDIA_PG_DRIFT_URL=postgresql+psycopg2://... pytest test_schema_drift_pg.py
(без URL — skip; с MEDIA_REQUIRE_PG_TESTS=1 отсутствие URL — ошибка сбора,
чтобы CI-шаг не мог позеленеть, не исполнив гейт).
"""
from __future__ import annotations

import os
import pathlib
from typing import Callable, Iterator

import pytest
from sqlalchemy import Column, Integer, MetaData, create_engine, inspect, text
from sqlalchemy.engine import Engine

PG_URL = os.environ.get("MEDIA_PG_DRIFT_URL")
if not PG_URL:
    if os.environ.get("MEDIA_REQUIRE_PG_TESTS") == "1":
        raise RuntimeError(
            "MEDIA_REQUIRE_PG_TESTS=1, но MEDIA_PG_DRIFT_URL не задан — "
            "дрейф-гейт media не может быть пропущен"
        )
    pytest.skip("MEDIA_PG_DRIFT_URL не задан (гейт только для PostgreSQL)", allow_module_level=True)

from app.models.media import Base  # noqa: E402 — после skip-гарда
from run_migrations import apply_migrations  # noqa: E402

BASELINE_SQL = pathlib.Path(__file__).parent / "schema_baseline" / "pre_0001.sql"

# Модель удалена (241972d6), таблица на существующих БД осталась — не дрейф.
ORPHAN_TABLES = frozenset({"media_upload_sessions"})

Snapshot = dict  # {table: {aspect: normalized value}}


# ---------------------------------------------------------------- helpers ---

def _schema_engine(schema: str) -> Engine:
    """Движок, у которого всё неквалифицированное живёт в `schema`."""
    return create_engine(PG_URL, connect_args={"options": f"-csearch_path={schema}"})


def _reset_schema(schema: str) -> Engine:
    admin = create_engine(PG_URL)
    with admin.begin() as conn:
        conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    admin.dispose()
    return _schema_engine(schema)


def _unqualify(default: str | None, schema: str) -> str | None:
    """SQLAlchemy при явном schema= квалифицирует sequence в nextval(...) —
    убираем имя служебной схемы, иначе эталон и кандидат разойдутся на пустом месте."""
    if default is None:
        return None
    return default.replace(f'"{schema}".', "").replace(f"{schema}.", "")


def _snapshot(engine: Engine, schema: str) -> Snapshot:
    insp = inspect(engine)
    snap: Snapshot = {}
    for table in sorted(insp.get_table_names(schema=schema)):
        snap[table] = {
            "columns": {
                c["name"]: (str(c["type"]), c["nullable"], _unqualify(c.get("default"), schema))
                for c in insp.get_columns(table, schema=schema)
            },
            "pk": tuple(insp.get_pk_constraint(table, schema=schema)["constrained_columns"]),
            "unique": sorted(
                (u["name"], tuple(u["column_names"]))
                for u in insp.get_unique_constraints(table, schema=schema)
            ),
            "indexes": sorted(
                (
                    i["name"],
                    tuple(i["column_names"]),
                    bool(i["unique"]),
                    (i.get("dialect_options") or {}).get("postgresql_where"),
                )
                for i in insp.get_indexes(table, schema=schema)
            ),
            "fks": sorted(
                (tuple(f["constrained_columns"]), f["referred_table"], tuple(f["referred_columns"]))
                for f in insp.get_foreign_keys(table, schema=schema)
            ),
        }
    return snap


def _diff(expected: Snapshot, actual: Snapshot, allow_extra: frozenset = frozenset()) -> list[str]:
    """Человекочитаемый список расхождений БД (`actual`) с моделями (`expected`)."""
    problems: list[str] = []
    for table in sorted(set(expected) - set(actual)):
        problems.append(f"{table}: таблица есть в моделях, нет в БД")
    for table in sorted(set(actual) - set(expected) - allow_extra):
        problems.append(f"{table}: таблица есть в БД, нет в моделях")
    for table in sorted(set(expected) & set(actual)):
        exp, act = expected[table], actual[table]
        exp_cols, act_cols = exp["columns"], act["columns"]
        for col in sorted(set(exp_cols) - set(act_cols)):
            problems.append(f"{table}.{col}: колонка есть в модели, нет в БД (забыта миграция?)")
        for col in sorted(set(act_cols) - set(exp_cols)):
            problems.append(f"{table}.{col}: колонка есть в БД, нет в модели")
        for col in sorted(set(exp_cols) & set(act_cols)):
            if exp_cols[col] != act_cols[col]:
                problems.append(
                    f"{table}.{col}: (type, nullable, default) модель={exp_cols[col]} БД={act_cols[col]}"
                )
        for aspect in ("pk", "unique", "indexes", "fks"):
            if exp[aspect] != act[aspect]:
                problems.append(f"{table}: {aspect} модель={exp[aspect]} БД={act[aspect]}")
    return problems


def _models_snapshot(metadata: MetaData, schema: str) -> Snapshot:
    engine = _reset_schema(schema)
    try:
        metadata.create_all(bind=engine)
        return _snapshot(engine, schema)
    finally:
        engine.dispose()


def _fresh_snapshot(metadata: MetaData, schema: str) -> Snapshot:
    engine = _reset_schema(schema)
    try:
        metadata.create_all(bind=engine)
        with engine.begin() as conn:
            apply_migrations(conn)
        return _snapshot(engine, schema)
    finally:
        engine.dispose()


def _upgrade_snapshot(metadata: MetaData, schema: str) -> Snapshot:
    """Порядок прода: media-migrate ДО старта сервиса (create_all в init_db)."""
    engine = _reset_schema(schema)
    try:
        with engine.begin() as conn:
            conn.execute(text(BASELINE_SQL.read_text()))
            apply_migrations(conn)
        metadata.create_all(bind=engine)
        return _snapshot(engine, schema)
    finally:
        engine.dispose()


@pytest.fixture
def pg_schema() -> Iterator[Callable[[str], str]]:
    created: list[str] = []

    def make(suffix: str) -> str:
        name = f"media_drift_{suffix}"
        created.append(name)
        return name

    yield make
    admin = create_engine(PG_URL)
    with admin.begin() as conn:
        for name in created:
            conn.execute(text(f'DROP SCHEMA IF EXISTS "{name}" CASCADE'))
    admin.dispose()


# ------------------------------------------------------------------ tests ---

def test_fresh_db_create_all_plus_migrations_matches_models(pg_schema):
    expected = _models_snapshot(Base.metadata, pg_schema("ref"))
    actual = _fresh_snapshot(Base.metadata, pg_schema("fresh"))
    assert expected, "эталон пуст — create_all ничего не создал"
    problems = _diff(expected, actual)
    assert not problems, "fresh: create_all + migrations ≠ модели:\n" + "\n".join(problems)


def test_existing_db_baseline_plus_migrations_matches_models(pg_schema):
    expected = _models_snapshot(Base.metadata, pg_schema("ref"))
    actual = _upgrade_snapshot(Base.metadata, pg_schema("upgrade"))
    problems = _diff(expected, actual, allow_extra=ORPHAN_TABLES)
    assert not problems, (
        "upgrade: существующая БД + migrations/*.sql + create_all ≠ модели — "
        "новой колонке/индексу нужен migrations/NNNN_*.sql:\n" + "\n".join(problems)
    )


def test_gate_catches_model_column_without_migration(pg_schema):
    """Самопроверка гейта: колонка только в модели обязана дать дрейф."""
    mutated = MetaData()
    for table in Base.metadata.tables.values():
        table.to_metadata(mutated)
    mutated.tables["media_files"].append_column(Column("drift_probe", Integer, nullable=True))

    expected = _models_snapshot(mutated, pg_schema("probe_ref"))
    actual = _upgrade_snapshot(mutated, pg_schema("probe_upgrade"))
    problems = _diff(expected, actual, allow_extra=ORPHAN_TABLES)
    assert any("media_files.drift_probe" in p for p in problems), problems
