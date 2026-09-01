"""A4 — ratchet-гейт broad-except в money-path модулях
(AUD5-ARCH-5 / AUD5-CODE-13 / AUD3-27).

Волна A4 разделила судьбы ошибок в money-path'ах (create/accept/assign и
движки смен): SQLAlchemyError — logger.exception + re-raise (никаких
«безопасных» 0.5 / busy=True / [] / None), broad-except остался только там,
где он осознан (best-effort уведомления, rollback+raise, честный
error-envelope). Гейт держит достигнутый уровень AST-счётом: количество
``except Exception`` / голых ``except`` (в т.ч. Exception внутри tuple) на
файл не должно РАСТИ.

Гейт двунаправленный:

* счёт ВЫШЕ baseline — регресс: новый broad-except в money-path. Сузьте его
  (SQLAlchemyError + logger.exception + raise) или обоснуйте и осознанно
  поднимите baseline в паре с ревью;
* счёт НИЖЕ baseline — прогресс: обновите baseline вниз (ratchet), чтобы
  зафиксировать достигнутое.

Новые файлы в пакетах shift_assignment_service / shift_planning_service
обязаны появиться в BASELINE — иначе гейт падает (защита от тихого выноса
broad-except в необъявленный модуль).
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Точный счёт ПОСЛЕ волны A4 (2026-08-14). Двигать только осознанно:
# вниз — при дальнейшем сужении, вверх — никогда без ревью.
BASELINE: dict[str, int] = {
    "uk_management_bot/main.py": 19,
    "uk_management_bot/services/request_service.py": 4,
    # BUG-185 (2026-09-01): −2 — ретайрены _notify_group_assignment /
    # _notify_executor_assignment (broad-except глотал AttributeError
    # несуществующего send_notification).
    "uk_management_bot/services/assignment_service.py": 4,
    "uk_management_bot/services/shift_assignment_service/__init__.py": 0,
    "uk_management_bot/services/shift_assignment_service/_types.py": 0,
    "uk_management_bot/services/shift_assignment_service/balancer.py": 1,
    "uk_management_bot/services/shift_assignment_service/conflicts.py": 0,
    "uk_management_bot/services/shift_assignment_service/scoring.py": 3,
    "uk_management_bot/services/shift_assignment_service/service.py": 8,
    "uk_management_bot/services/shift_planning_service/__init__.py": 0,
    "uk_management_bot/services/shift_planning_service/analytics.py": 6,
    "uk_management_bot/services/shift_planning_service/planning.py": 11,
    "uk_management_bot/services/shift_planning_service/rebalance.py": 1,
    "uk_management_bot/services/shift_planning_service/scoring.py": 1,
}

# Пакеты, где новые *.py обязаны попасть в BASELINE.
PACKAGE_GLOBS = [
    "uk_management_bot/services/shift_assignment_service/*.py",
    "uk_management_bot/services/shift_planning_service/*.py",
]


def _broad_except_count(path: Path) -> int:
    """AST-счёт ExceptHandler'ов: голый except, `except Exception`,
    `except (…, Exception, …)`."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    count = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler):
            continue
        t = node.type
        if t is None:
            count += 1
        elif isinstance(t, ast.Name) and t.id == "Exception":
            count += 1
        elif isinstance(t, ast.Tuple) and any(
            isinstance(e, ast.Name) and e.id == "Exception" for e in t.elts
        ):
            count += 1
    return count


def test_baseline_files_exist():
    """BASELINE не должен указывать на несуществующие файлы (переезд кода —
    повод обновить гейт, а не потерять охват)."""
    missing = [rel for rel in BASELINE if not (ROOT / rel).exists()]
    assert not missing, f"BASELINE указывает на несуществующие файлы: {missing}"


def test_new_package_modules_are_covered():
    """Новый модуль в money-path пакете обязан быть учтён в BASELINE."""
    uncovered = []
    for pattern in PACKAGE_GLOBS:
        for path in sorted(ROOT.glob(pattern)):
            rel = path.relative_to(ROOT).as_posix()
            if rel not in BASELINE:
                uncovered.append(rel)
    assert not uncovered, (
        "Модули money-path пакетов вне охвата гейта — добавьте в BASELINE "
        f"с фактическим счётом: {uncovered}"
    )


def test_broad_except_ratchet():
    grew: list[str] = []
    shrank: list[str] = []
    for rel, expected in BASELINE.items():
        actual = _broad_except_count(ROOT / rel)
        if actual > expected:
            grew.append(f"{rel}: {actual} > baseline {expected}")
        elif actual < expected:
            shrank.append(f"{rel}: {actual} < baseline {expected}")

    assert not grew, (
        "AUD5-ARCH-5 ratchet: broad-except в money-path вырос — сузьте "
        "(SQLAlchemyError + logger.exception + raise) или пересмотрите с ревью:\n"
        + "\n".join(grew)
    )
    assert not shrank, (
        "Broad-except стало МЕНЬШЕ — отлично: обновите BASELINE вниз, "
        "чтобы зафиксировать прогресс:\n" + "\n".join(shrank)
    )
