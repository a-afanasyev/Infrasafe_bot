"""AUD5-CODE-3/2: AST-гейт naive datetime в shift-домене.

Shift-колонки — `DateTime(timezone=True)` (timestamptz). Naive `datetime.now()`
записанный в такую колонку или сравненный с aware-значением из БД либо падает
(TypeError naive-vs-aware), либо тихо мис-сравнивается в SQL-фильтрах.

Гейт ловит четыре паттерна в SWEPT_FILES:
  (a) `datetime.now()`/`datetime.now(None)`/`datetime.now(tz=None)` и `datetime.utcnow()`;
  (b) `datetime.combine(...)` без `tzinfo` (ни keyword, ни 3-м позиционным);
  (c) `<expr>.replace(tzinfo=None)` (среди любых keyword'ов, не только single);
  (d) голый конструктор `datetime(y, m, d, ...)` без `tzinfo`.

Имя `datetime` резолвится через реальные import-статьи файла (`_resolve_datetime_names`),
включая алиасы (`from datetime import datetime as dt`, `import datetime as dt2`,
`import datetime` → `datetime.datetime`) — иначе алиасинг тривиально обходит гейт.

RED-механизм для query/сравнения-сайтов НАМЕРЕННО — этот AST-гейт, а не
поведенческий тест: тестовый движок — sqlite, а sqlite сравнивает datetime
как строки и не различает naive/aware — поведенческий тест не упадёт честно
там, где падает/съезжает только PostgreSQL (timestamptz).

`utils/shifts.py` (`is_on_shift_now_sync/async`) НАМЕРЕННО не в SWEPT_FILES —
naive-default там осознанное решение (см. модульный docstring), claim-
семантика — отдельный owner-decision, не часть этой волны.
"""

from __future__ import annotations

import ast
from pathlib import Path

from uk_management_bot.utils.datetime_utils import utc_now
from datetime import timezone, timedelta

PACKAGE_ROOT = Path(__file__).resolve().parents[2] / "uk_management_bot"

# Растёт по таскам плана (Task 1 → 2 → 3 → 4); финал = 8 файлов.
SWEPT_FILES: tuple[str, ...] = (
    "services/shift_service.py",
    "handlers/my_shifts.py",
    "handlers/shifts.py",
    "utils/shift_scheduler.py",
    "handlers/shift_management/assignment_a.py",
    "handlers/shift_management/assignment_b.py",
    "handlers/shift_management/analytics.py",
    "handlers/shift_management/manual_planning.py",
)


def _resolve_datetime_names(tree: ast.Module) -> tuple[set[str], set[str]]:
    """Names bound to the `datetime.datetime` class vs. the `datetime` module,
    resolved from this file's own import statements (handles aliasing)."""
    class_names: set[str] = set()
    module_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "datetime":
            for alias in node.names:
                if alias.name == "datetime":
                    class_names.add(alias.asname or alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "datetime":
                    module_names.add(alias.asname or alias.name)
    return class_names, module_names


def _is_datetime_class_ref(node: ast.expr, class_names: set[str], module_names: set[str]) -> bool:
    """Does `node` refer to the `datetime.datetime` class (directly or via `<module>.datetime`)?"""
    if isinstance(node, ast.Name) and node.id in class_names:
        return True
    if (isinstance(node, ast.Attribute) and node.attr == "datetime"
            and isinstance(node.value, ast.Name) and node.value.id in module_names):
        return True
    return False


def _has_tzinfo(node: ast.Call, *, positional_index: int) -> bool:
    """`tzinfo` supplied either positionally (see stdlib signature) or as a keyword."""
    if len(node.args) > positional_index:
        return True
    return any(kw.arg == "tzinfo" for kw in node.keywords)


def _is_naive_tz_arg(node: ast.Call) -> bool:
    """`now(None)` / `now(tz=None)` — explicit way to force a naive result."""
    if node.args:
        arg = node.args[0]
        return isinstance(arg, ast.Constant) and arg.value is None
    for kw in node.keywords:
        if kw.arg == "tz" and isinstance(kw.value, ast.Constant) and kw.value.value is None:
            return True
    return False


def _is_bare_datetime_now_or_utcnow(node: ast.Call, class_names: set[str], module_names: set[str]) -> bool:
    if not isinstance(node.func, ast.Attribute):
        return False
    if not _is_datetime_class_ref(node.func.value, class_names, module_names):
        return False
    if node.func.attr == "utcnow":
        return True
    if node.func.attr == "now" and not node.args and not node.keywords:
        return True
    if node.func.attr == "now" and _is_naive_tz_arg(node):
        return True
    return False


def _is_combine_without_tzinfo(node: ast.Call, class_names: set[str], module_names: set[str]) -> bool:
    if not isinstance(node.func, ast.Attribute) or node.func.attr != "combine":
        return False
    if not _is_datetime_class_ref(node.func.value, class_names, module_names):
        return False
    # combine(date, time, tzinfo) accepts tzinfo positionally (3rd arg) too.
    return not _has_tzinfo(node, positional_index=2)


def _is_replace_tzinfo_none(node: ast.Call) -> bool:
    if not isinstance(node.func, ast.Attribute) or node.func.attr != "replace":
        return False
    return any(
        kw.arg == "tzinfo" and isinstance(kw.value, ast.Constant) and kw.value.value is None
        for kw in node.keywords
    )


def _is_bare_naive_constructor(node: ast.Call, class_names: set[str], module_names: set[str]) -> bool:
    """`datetime(y, m, d, ...)` without `tzinfo` — naive by construction.

    `tzinfo` is the 8th positional parameter (year, month, day, hour, minute,
    second, microsecond, tzinfo).
    """
    if not _is_datetime_class_ref(node.func, class_names, module_names):
        return False
    if len(node.args) < 3:
        return False  # not a (year, month, day, ...) constructor call
    return not _has_tzinfo(node, positional_index=7)


def collect_violations(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    class_names, module_names = _resolve_datetime_names(tree)
    violations = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        line = node.lineno
        if _is_bare_datetime_now_or_utcnow(node, class_names, module_names):
            violations.append(f"{path}:{line}: naive datetime.now()/utcnow() — используй utc_now()")
        elif _is_combine_without_tzinfo(node, class_names, module_names):
            violations.append(f"{path}:{line}: datetime.combine(...) без tzinfo= — добавь tzinfo=timezone.utc")
        elif _is_replace_tzinfo_none(node):
            violations.append(f"{path}:{line}: .replace(tzinfo=None) — naive-strip обход запрещён")
        elif _is_bare_naive_constructor(node, class_names, module_names):
            violations.append(f"{path}:{line}: datetime(...) без tzinfo= — naive-конструктор запрещён")
    return violations


def test_shift_domain_files_are_tz_aware():
    all_violations: list[str] = []
    for rel in SWEPT_FILES:
        path = PACKAGE_ROOT / rel
        all_violations.extend(collect_violations(path))
    assert not all_violations, "\n" + "\n".join(all_violations)


def test_utc_now_is_aware():
    now = utc_now()
    assert now.tzinfo is timezone.utc
    assert now.utcoffset() == timedelta(0)
