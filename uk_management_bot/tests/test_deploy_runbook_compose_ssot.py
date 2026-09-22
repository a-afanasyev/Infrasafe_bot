"""SSOT-гейт набора compose-файлов в документах деплоя (A9-P1-3).

До гейта канон uk-deploy для profk перечислял `yml+profk`, хотя на profk с
2026-09-06 поднят payments-overlay: пересоздание `api` по канону молча снимало
`PAYMENT_SERVICE_URL/TOKEN`, и «Контроль платежей» отвечал 404/503. RUNBOOK при
этом откатывал любую площадку через `media.yml`, а `make prod-up` падал на `:?`.

Источник истины — таблица «Площадка → COMPOSE» в `.claude/skills/uk-deploy/SKILL.md`.
Гейт держит три вещи: каждый overlay репо упомянут в таблице; строка profk
содержит payments; ни одна команда `docker compose` в документах деплоя не
поднимает profk-стек без payments. Внутри образа без `.claude` — skip (как у
`test_ci_service_coverage.py`); в `make test-ci` файлы монтируются пофайлово.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL = REPO_ROOT / ".claude" / "skills" / "uk-deploy" / "SKILL.md"
DEPLOY_DOCS = (
    SKILL,
    REPO_ROOT / "docs" / "ops" / "RUNBOOK.md",
    REPO_ROOT / "docs" / "ROLLBACK.md",
    REPO_ROOT / "docs" / "tech" / "PAYMENT_CONTROL.md",
    REPO_ROOT / "docs" / "DEPLOYMENT_CHECKLIST.md",
    REPO_ROOT / "docs" / "tech" / "ARCHITECTURE.md",
    REPO_ROOT / "docs" / "tech" / "ARCHITECTURE_DIAGRAMS.md",
    REPO_ROOT / "docker-compose.profk.yml",
)
# dev-стек — не прод-площадка, в таблицу не входит.
NON_PROD_OVERLAYS = {"docker-compose.dev.yml"}
PROFK = "docker-compose.profk.yml"
PAYMENTS = "docker-compose.payments.yml"

pytestmark = pytest.mark.skipif(
    not SKILL.exists(), reason="в образе нет .claude/ — гейт гоняется в CI и make test-ci"
)


def _site_table(text: str) -> list[str]:
    """Строки таблицы «Площадка → COMPOSE» (первая таблица с колонкой `COMPOSE`)."""
    lines = text.splitlines()
    start = next(
        (i for i, line in enumerate(lines) if line.startswith("| Площадка") and "COMPOSE" in line),
        None,
    )
    assert start is not None, "в SKILL нет таблицы «Площадка → COMPOSE»"
    rows = []
    for line in lines[start + 2:]:
        if not line.startswith("|"):
            break
        rows.append(line)
    return rows


def profk_commands_without_payments(text: str) -> list[str]:
    """Команды/наборы `-f`, поднимающие profk-стек без payments-overlay."""
    return [
        line.strip()
        for line in text.splitlines()
        if PROFK in line
        and ("docker compose" in line or "-f docker-compose.yml" in line)
        and PAYMENTS not in line
    ]


COMPOSE_GUARD = "${COMPOSE:?"


def unguarded_compose_blocks(text: str) -> list[str]:
    """Code-fence'ы, где `docker compose $COMPOSE` есть, а fail-fast guard'а нет.

    Неприсвоенная `$COMPOSE` разворачивается в пустоту, и скопированная
    команда молча собирает/поднимает стек без overlay'ев — хуже, чем старые
    неполные литералы. Guard `: "${COMPOSE:?…}"` в том же блоке роняет её сразу.
    """
    offenders = []
    for i, block in enumerate(text.split("```")):
        if i % 2 == 1 and "docker compose $COMPOSE" in block and COMPOSE_GUARD not in block:
            offenders.append(block.strip().splitlines()[0] if block.strip() else "<пустой блок>")
    return offenders


def test_every_prod_overlay_is_in_site_table():
    rows = "\n".join(_site_table(SKILL.read_text(encoding="utf-8")))
    overlays = sorted(
        p.name for p in REPO_ROOT.glob("docker-compose.*.yml") if p.name not in NON_PROD_OVERLAYS
    )
    assert overlays, "не найдено ни одного overlay — гейт ничего не проверяет"
    missing = [name for name in overlays if name not in rows]
    assert not missing, f"overlay не упомянут в таблице SKILL: {missing}"


def test_profk_row_includes_payments():
    profk = [row for row in _site_table(SKILL.read_text(encoding="utf-8")) if PROFK in row]
    assert len(profk) == 1, "в таблице SKILL должна быть ровно одна строка profk"
    assert PAYMENTS in profk[0], "payments включён на profk — overlay обязан быть в его наборе"


@pytest.mark.parametrize("doc", DEPLOY_DOCS, ids=lambda p: p.name)
def test_no_profk_command_without_payments(doc: Path):
    if not doc.exists():
        pytest.skip(f"{doc.name} не смонтирован")
    offenders = profk_commands_without_payments(doc.read_text(encoding="utf-8"))
    assert not offenders, f"{doc.name}: profk-команды без payments: {offenders}"


@pytest.mark.parametrize("doc", DEPLOY_DOCS, ids=lambda p: p.name)
def test_compose_variable_is_guarded(doc: Path):
    if not doc.exists():
        pytest.skip(f"{doc.name} не смонтирован")
    offenders = unguarded_compose_blocks(doc.read_text(encoding="utf-8"))
    assert not offenders, f"{doc.name}: блоки с $COMPOSE без guard: {offenders}"


def test_gate_catches_synthetic_violation():
    """Самопроверка: гейт, который не ловит нарушитель, молча ничего не проверяет."""
    bad = f"doppler run -- docker compose -f docker-compose.yml -f {PROFK} up -d api"
    good = f"doppler run -- docker compose -f docker-compose.yml -f {PROFK} -f {PAYMENTS} up -d api"
    assert profk_commands_without_payments(bad) == [bad]
    assert profk_commands_without_payments(good) == []
    assert profk_commands_without_payments(f"| Compose | `-f docker-compose.yml -f {PROFK}` |")
    unguarded = "```bash\ndoppler run -- docker compose $COMPOSE up -d api\n```"
    guarded = '```bash\n: "${COMPOSE:?x}"\ndoppler run -- docker compose $COMPOSE up -d api\n```'
    assert unguarded_compose_blocks(unguarded)
    assert unguarded_compose_blocks(guarded) == []
