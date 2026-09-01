"""AUD5-CODE-10 — ратчет функций длиннее 100 строк в зоне бота.

Режим «инкрементально при касании» класс не сдерживал: счёт вырос 44 → 48
(аудит 2026-08-19) → 49 (снимок этого baseline). Ратчет замораживает рост
per-file baseline'ом по образцу test_aud5_arch5_broad_except_ratchet.py:

* счёт ВЫШЕ baseline — регресс: новая/разросшаяся функция >100 строк.
  Раскройте её (выделите под-шаги) — baseline вверх не двигается никогда;
* счёт НИЖЕ baseline — прогресс: обновите число вниз (файл на нуле — снять
  строку целиком);
* новый файл обязан рождаться без функций >100 строк;
* файл baseline исчез из дерева (переезд/ретайр) — обновить гейт.

Метрика: def/async def с (end_lineno - lineno + 1) > 100 в
uk_management_bot/ вне tests/ и локального venv/ (мусор AUD5-JUNK-5 —
не наша зона). Вложенные функции считаются самостоятельно; декораторы в
длину не входят (lineno указывает на сам def).
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

_LIMIT = 100

_EXCLUDED_PREFIXES = (
    "uk_management_bot/tests/",
    "uk_management_bot/venv/",
)

# Снимок 2026-09-01 (40 файлов / 49 функций). Двигать только вниз.
BASELINE: dict[str, int] = {
    "uk_management_bot/api/lifecycle.py": 1,
    "uk_management_bot/api/requests/router.py": 1,
    "uk_management_bot/api/requests/stats_router.py": 1,
    "uk_management_bot/api/routes/media_proxy.py": 1,
    "uk_management_bot/api/work_reports/public_router.py": 1,
    "uk_management_bot/handlers/admin/actions.py": 1,
    "uk_management_bot/handlers/admin/shared.py": 1,
    "uk_management_bot/handlers/admin/views.py": 2,
    "uk_management_bot/handlers/auth.py": 1,
    "uk_management_bot/handlers/group_intake.py": 2,
    "uk_management_bot/handlers/my_shifts/viewing.py": 1,
    "uk_management_bot/handlers/requests/create.py": 1,
    "uk_management_bot/handlers/requests/executor.py": 1,
    "uk_management_bot/handlers/requests/listing.py": 3,
    "uk_management_bot/handlers/requests/myrequests.py": 2,
    "uk_management_bot/handlers/shift_management/assignment_a.py": 1,
    "uk_management_bot/handlers/shift_management/assignment_b.py": 1,
    "uk_management_bot/handlers/unaccepted_requests.py": 1,
    "uk_management_bot/keyboards/user_management.py": 1,
    "uk_management_bot/main.py": 1,
    "uk_management_bot/middlewares/auth.py": 1,
    "uk_management_bot/services/auth_service.py": 1,
    "uk_management_bot/services/inbound_alert.py": 1,
    "uk_management_bot/services/metrics_manager.py": 2,
    "uk_management_bot/services/profile_service.py": 1,
    "uk_management_bot/services/reconciliation.py": 2,
    "uk_management_bot/services/request_service.py": 1,
    "uk_management_bot/services/shift_analytics.py": 2,
    "uk_management_bot/services/shift_assignment_service/service.py": 2,
    "uk_management_bot/services/shift_planning_service/analytics.py": 1,
    "uk_management_bot/services/shift_planning_service/planning.py": 1,
    "uk_management_bot/services/shift_transfer_service.py": 1,
    "uk_management_bot/services/webhook_sender.py": 1,
    "uk_management_bot/services/work_reports/autopublish.py": 1,
    "uk_management_bot/services/work_reports/reconcile.py": 1,
    "uk_management_bot/services/work_reports/saga.py": 1,
    "uk_management_bot/services/work_reports/sync.py": 1,
    "uk_management_bot/utils/button_texts.py": 1,
    "uk_management_bot/utils/request_workflow/planner.py": 1,
    "uk_management_bot/utils/shift_scheduler.py": 1,
}


def _long_function_count(path: Path) -> int:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return sum(
        1
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.end_lineno - node.lineno + 1 > _LIMIT
    )


def _scanned_files():
    for path in sorted((ROOT / "uk_management_bot").rglob("*.py")):
        rel = path.relative_to(ROOT).as_posix()
        if rel.startswith(_EXCLUDED_PREFIXES):
            continue
        yield path, rel


def test_baseline_is_consistent():
    """Нулевые и висячие записи запрещены — baseline описывает только факт."""
    zeros = [rel for rel, n in BASELINE.items() if n <= 0]
    assert not zeros, f"нулевые записи — снимите строки целиком: {zeros}"
    excluded = [rel for rel in BASELINE if rel.startswith(_EXCLUDED_PREFIXES)]
    assert not excluded, f"baseline лезет в исключённые зоны: {excluded}"


def test_long_function_ratchet():
    grew: list[str] = []
    shrank: list[str] = []
    seen: set[str] = set()
    for path, rel in _scanned_files():
        actual = _long_function_count(path)
        expected = BASELINE.get(rel, 0)
        seen.add(rel)
        if actual > expected:
            grew.append(f"{rel}: {actual} > baseline {expected}")
        elif actual < expected:
            shrank.append(f"{rel}: {actual} < baseline {expected}")

    assert not grew, (
        "AUD5-CODE-10 ratchet: функций >100 строк стало больше — раскройте "
        "новую/разросшуюся (baseline вверх не двигается):\n" + "\n".join(grew)
    )
    assert not shrank, (
        "Длинных функций стало МЕНЬШЕ — отлично: обновите baseline вниз "
        "(файл на нуле — снять строку):\n" + "\n".join(shrank)
    )

    gone = set(BASELINE) - seen
    assert not gone, (
        "Файлы baseline исчезли из дерева (переезд/ретайр) — обновите гейт: "
        f"{sorted(gone)}"
    )
