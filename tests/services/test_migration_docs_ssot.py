"""AUD7-ENG-05: команда миграций и документация согласованы с ролью migrator.

После PR-7 схемой владеет `uk_migration_owner`, миграции идут one-shot сервисом
`migrate` под `uk_migrator` (scripts/entrypoint-migrate.sh), а runtime-контейнер
api делает только read-only preflight. Makefile и документация всё ещё
предлагали DDL из runtime API (`docker exec uk-management-api alembic upgrade`),
искали сообщение миграции в логах api (его пишет entrypoint migrate) и
называли другой TTL refresh-токена. Гейт статический — только текст.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from uk_management_bot.api.auth.service import REFRESH_TOKEN_EXPIRE_DAYS

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCS = ("README.md", "docs/ops/RUNBOOK.md", "docs/tech/ARCHITECTURE.md", "Makefile")

# DDL из runtime-контейнера: `docker exec uk-management-api … alembic upgrade|downgrade`.
RUNTIME_DDL = re.compile(r"docker exec\s+(-it\s+)?uk-management-api\b[^\n]*alembic\s+(upgrade|downgrade|stamp)")


def _read(rel: str) -> str:
    path = REPO_ROOT / rel
    if not path.exists():
        pytest.skip(f"{rel} отсутствует (запуск внутри образа, не чекаут)")
    return path.read_text(encoding="utf-8")


def test_makefile_migration_target_uses_one_shot_migrate_service():
    text = _read("Makefile")
    match = re.search(r"^migration-upgrade:.*\n((?:\t.*\n)+)", text, re.M)
    assert match, "цель migration-upgrade не найдена"
    body = match.group(1)
    assert "uk-management-api" not in body, "migration-upgrade гоняет DDL из runtime API"
    assert re.search(r"run --rm\b.*\bmigrate\b", body), "migration-upgrade обязан звать сервис migrate"


@pytest.mark.parametrize("rel", DOCS)
def test_docs_do_not_suggest_ddl_from_runtime_api(rel: str):
    hits = [m.group(0) for m in RUNTIME_DDL.finditer(_read(rel))]
    assert not hits, f"{rel}: DDL из runtime-контейнера api: {hits}"


def test_runbook_looks_for_migration_message_where_it_is_written():
    """«Migrations complete.» печатает scripts/entrypoint-migrate.sh — не api."""
    text = _read("docs/ops/RUNBOOK.md")
    assert "Migrations complete" in _read("scripts/entrypoint-migrate.sh")
    bad = [line for line in text.splitlines() if "docker logs uk-management-api" in line and "Migrations complete" in line]
    assert not bad, f"RUNBOOK ищет сообщение миграции в логах api: {bad}"


def test_architecture_refresh_ttl_matches_code():
    text = _read("docs/tech/ARCHITECTURE.md")
    m = re.search(r"Web-SPA\s*—\s*(\d+)\s*дн", text)
    assert m, "в ARCHITECTURE нет срока refresh для Web-SPA"
    assert int(m.group(1)) == REFRESH_TOKEN_EXPIRE_DAYS, (
        f"ARCHITECTURE: {m.group(1)} дней, код: {REFRESH_TOKEN_EXPIRE_DAYS}"
    )
