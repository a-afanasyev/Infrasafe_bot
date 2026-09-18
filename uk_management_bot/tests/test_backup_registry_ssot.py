"""SSOT-гейт: каждый stateful postgres-контейнер из compose есть в реестре бэкапов.

AUD7-ENG-07: репозиторный `scripts/backup-db.sh` дампил одну БД и давно был
мёртв (реальный механизм — кросс-бэкап хост-пиров вне репо), а реестра «что,
где, как часто, сколько хранится, кто владелец, RPO/RTO» в репо не было —
покрытие новой БД (uk_media, payment) каждый раз обнаруживал внешний аудит.
Реестр — docs/ops/BACKUPS.md; источник истины для «какие БД есть» — compose
(образ postgres*/postgis* с container_name). Гейт статический.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
REGISTRY = REPO_ROOT / "docs" / "ops" / "BACKUPS.md"
COMPOSE_FILES = (
    "docker-compose.yml",
    "docker-compose.profk.yml",
    "docker-compose.media.yml",
    "docker-compose.payments.yml",
)
RETIRED = ("scripts/backup-db.sh", "scripts/crontab.production")


class _ComposeLoader(yaml.SafeLoader):
    """Compose-теги `!override`/`!reset` — как обычные узлы."""


def _construct_plain(loader: yaml.SafeLoader, node: yaml.Node):
    if isinstance(node, yaml.MappingNode):
        return loader.construct_mapping(node)
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node)
    return loader.construct_scalar(node)


for _tag in ("!override", "!reset"):
    _ComposeLoader.add_constructor(_tag, _construct_plain)


def _postgres_containers() -> set[str]:
    found: set[str] = set()
    for name in COMPOSE_FILES:
        path = REPO_ROOT / name
        if not path.exists():
            pytest.skip(f"{name} отсутствует (запуск внутри образа, не чекаут)")
        data = yaml.load(path.read_text(), Loader=_ComposeLoader)  # noqa: S506 — SafeLoader-наследник
        for service in (data.get("services") or {}).values():
            image = str((service or {}).get("image") or "")
            container = (service or {}).get("container_name")
            if container and re.match(r"^(postgres|postgis)[:/]", image):
                found.add(container)
    return found


def test_registry_lists_every_postgres_container():
    containers = _postgres_containers()
    assert containers, "в compose не найдено ни одного postgres-контейнера — поправь гейт"
    if not REGISTRY.exists():
        pytest.fail(f"нет реестра бэкапов {REGISTRY.relative_to(REPO_ROOT)}")
    text = REGISTRY.read_text(encoding="utf-8")
    missing = sorted(c for c in containers if c not in text)
    assert not missing, f"postgres-контейнеры без записи в docs/ops/BACKUPS.md: {missing}"


def test_registry_covers_all_databases_of_shared_container():
    """uk-postgres держит две БД (main + uk_media) — обе обязаны быть в реестре."""
    if not REGISTRY.exists():
        pytest.fail("нет реестра бэкапов docs/ops/BACKUPS.md")
    text = REGISTRY.read_text(encoding="utf-8")
    for db in ("uk_media", "resource_accounting", "payment_control"):
        assert db in text, f"БД {db} нет в реестре"
    assert "RPO" in text and "RTO" in text, "в реестре нет RPO/RTO"


@pytest.mark.parametrize("rel", RETIRED)
def test_dead_repo_backup_script_is_retired(rel: str):
    """Мёртвый одно-БД скрипт вводил в заблуждение («репо бэкапит только main»)."""
    assert not (REPO_ROOT / rel).exists(), f"{rel} всё ещё в репо — списан в AUD7-ENG-07"
