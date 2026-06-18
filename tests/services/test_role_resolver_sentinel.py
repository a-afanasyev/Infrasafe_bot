"""ARCH-07 / PR-30 sentinel: доступ к legacy-роли ``User.role`` — только в резолвере.

DoD PR-30 (closure-plan §4, «архитектурное выпрямление»): обращения к устаревшей
колонке ``User.role`` / атрибуту ``user.role`` в боевой логике должны идти через
единый резолвер ``utils/auth_helpers`` (``get_user_roles`` / ``get_active_role`` /
``legacy_role_filter`` / ``sync_legacy_role``). Разрешены только сам резолвер и
модель ``database/models/user.py`` (определение колонки + ``__repr__``).

Гейт статический (AST): считаем именно узлы ``Attribute`` с ``.role`` — строки
(локаль-ключи вида ``'employee_management.role'``) и комментарии не ловятся.
Любой новый прямой доступ к legacy-роли вне резолвера ломает тест намеренно —
сначала проведите его через ``auth_helpers``. В PR-31 (дроп колонки) тест
обновляется/снимается вместе с удалением ``User.role``.
"""
import ast
import pathlib

PKG_ROOT = pathlib.Path(__file__).resolve().parents[2] / "uk_management_bot"

# Файлы, которым РАЗРЕШЕНО ссылаться на legacy-роль (резолвер + модель).
ALLOWED = {
    "utils/auth_helpers.py",
    "database/models/user.py",
}

# Владельцы ``.role``, не являющиеся колонкой User (Pydantic-боди запроса и т.п.).
NON_USER_OWNERS = {"body"}

_SKIP_PARTS = {"tests", "venv", ".venv", "__pycache__", "site-packages"}


def _attr_owner(node: ast.Attribute) -> str:
    value = node.value
    if isinstance(value, ast.Name):
        return value.id
    if isinstance(value, ast.Attribute):
        return value.attr
    return "<expr>"


def _iter_modules():
    for path in PKG_ROOT.rglob("*.py"):
        parts = path.relative_to(PKG_ROOT).parts
        if any(p in _SKIP_PARTS for p in parts) or parts[-1].startswith("test_"):
            continue
        yield path.relative_to(PKG_ROOT).as_posix(), path


def test_legacy_role_access_only_in_resolver():
    offenders: dict[str, list[int]] = {}
    for rel, path in _iter_modules():
        if rel in ALLOWED:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:  # pragma: no cover - не наша забота здесь
            continue
        lines = [
            node.lineno
            for node in ast.walk(tree)
            if isinstance(node, ast.Attribute)
            and node.attr == "role"
            and _attr_owner(node) not in NON_USER_OWNERS
        ]
        if lines:
            offenders[rel] = sorted(lines)

    assert not offenders, (
        "Прямой доступ к legacy `User.role` вне резолвера (ARCH-07/PR-30). "
        "Проведите через utils/auth_helpers: get_user_roles / get_active_role / "
        f"legacy_role_filter / sync_legacy_role. Нарушители: {offenders}"
    )
