"""SSOT-гейт: список access-domain таблиц продублирован в 3 файлах руками.

Комментарий в `alembic/versions/0001_prc05_initial_baseline.py` (§ACL) требует:
добавил access-domain таблицу — обнови ВСЕ места, иначе она тихо получит
блáнкет-грант `uk_app_rw` (полный CRUD боту/API) и НЕ получит грантов
`access_app_rw`, под которым ходит access-api. Требование было
comment-only, поэтому и не соблюдено: `parking_spots` и
`parking_spot_assignments` создавались тем же baseline, но ни в один из трёх
списков не попали — access-api получал `permission denied for table
parking_spot_assignments` (500 на `GET /api/v1/access/my/spots`) с самого
PRC-05, а бот/API сохраняли полный DML на эти таблицы.

Гейт статический (парсит файлы, БД не нужна) — работает в обоих наборах.
Источник истины для «что такое access-domain таблица» — `__tablename__`
моделей в `access_control/`: именно их обслуживает access-api.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
BASELINE = REPO_ROOT / "alembic" / "versions" / "0001_prc05_initial_baseline.py"
ACL_RECONCILE = REPO_ROOT / "uk_management_bot" / "dbops" / "acl_reconcile.py"
DBA_TRANSFER = REPO_ROOT / "scripts" / "dba_ownership_transfer.sql"


def _model_tables() -> set[str]:
    """`__tablename__` всех моделей access_control (без тестовых фикстур)."""
    tables: set[str] = set()
    for path in (REPO_ROOT / "access_control").rglob("*.py"):
        if "tests" in path.parts:
            continue
        tables.update(
            re.findall(r'__tablename__\s*=\s*["\']([a-z0-9_]+)["\']', path.read_text())
        )
    return tables


def _sql_array(text: str, name: str) -> set[str]:
    match = re.search(rf"{name} text\[\] := ARRAY\[(.*?)\];", text, re.S)
    assert match, f"массив {name} не найден — изменилась форма объявления, поправь гейт"
    return set(re.findall(r"'([a-z0-9_]+)'", match.group(1)))


@pytest.fixture(scope="module")
def model_tables() -> set[str]:
    tables = _model_tables()
    assert tables, "не найдено ни одной модели в access_control/ — поправь гейт"
    return tables


def test_migrations_grant_every_access_domain_table(model_tables):
    """Каждая таблица моделей получила гранты access_app_rw в какой-то миграции.

    Baseline 0001 уже применён на обоих продах, поэтому дополнения к ACL едут
    отдельными миграциями (0007 и далее) с теми же именами массивов
    (`immut`/`other`) — суммируем по всем файлам versions/, а не только по 0001.
    """
    granted: set[str] = set()
    for path in sorted(BASELINE.parent.glob("0*.py")):
        text = path.read_text()
        for name in ("immut", "other"):
            if f"{name} text[] := ARRAY[" in text:
                granted |= _sql_array(text, name)
    assert granted == model_tables, (
        "ACL-массивы миграций расходятся с моделями access_control; без грантов "
        f"access_app_rw остаются: {sorted(model_tables - granted)}; "
        f"лишние в массивах: {sorted(granted - model_tables)}"
    )


def test_acl_reconcile_list_matches_models(model_tables):
    """ACCESS_DOMAIN_TABLES == таблицы моделей: иначе uk_app_rw не отзывается."""
    match = re.search(
        r"ACCESS_DOMAIN_TABLES = \[(.*?)\]", ACL_RECONCILE.read_text(), re.S
    )
    assert match, "ACCESS_DOMAIN_TABLES не найден — поправь гейт"
    listed = set(re.findall(r'"([a-z0-9_]+)"', match.group(1)))
    assert listed == model_tables, (
        "ACCESS_DOMAIN_TABLES расходится с моделями access_control; блáнкет-грант "
        f"uk_app_rw останется на: {sorted(model_tables - listed)}"
    )


def test_ownership_transfer_excludes_every_access_domain_table(model_tables):
    """excluded_tables cutover-скрипта == таблицы моделей (важно на fresh-install)."""
    if not DBA_TRANSFER.exists():
        # В образ бота каталог scripts/ не копируется — гейт живёт для CI и dev,
        # где чекаут полный. Молчаливого прохода нет: skip виден в отчёте.
        pytest.skip(f"{DBA_TRANSFER} отсутствует (запуск внутри образа, не чекаут)")
    excluded = _sql_array(DBA_TRANSFER.read_text(), "excluded_tables")
    assert excluded == model_tables, (
        "excluded_tables в dba_ownership_transfer.sql расходится с моделями "
        f"access_control; bulk-грант uk_app_rw заденет: {sorted(model_tables - excluded)}"
    )
