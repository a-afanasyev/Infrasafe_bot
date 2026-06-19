"""PR-31 / DB-060 sentinel: атрибута ``User.role`` БОЛЬШЕ НЕТ — ни одного ``.role``.

PR-30 свёл доступ к legacy-роли к резолверу; PR-31 удалил саму колонку
``users.role`` (миграция 022) и переключил нутро ``utils/auth_helpers``
(legacy_role_filter / sync_legacy_role / legacy_primary_role) на ``roles`` +
``active_role``. Теперь источник истины ролей — ``user.roles`` (JSON) и
``user.active_role``; обращение к ``user.role`` упало бы в AttributeError.

Гейт статический (AST): считаем узлы ``Attribute`` с ``.role`` во ВСЁМ пакете
(allowlist пуст — даже резолвер и модель больше не должны их иметь). Строки
(локаль-ключи) и комментарии не ловятся. Исключение — ``.role`` на не-User
владельцах (Pydantic-боди ``body.role`` и т.п.).
"""
import ast
import pathlib

PKG_ROOT = pathlib.Path(__file__).resolve().parents[2] / "uk_management_bot"

# PR-31: legacy-колонка удалена — ни одному файлу больше нельзя ссылаться на .role.
ALLOWED: set[str] = set()

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


def test_no_legacy_role_attribute_access():
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
        "Доступ к удалённой колонке `User.role` (DB-060/PR-31 — колонки больше нет, "
        "это AttributeError в рантайме). Используйте user.roles / user.active_role "
        "или резолвер utils/auth_helpers (get_user_roles / get_active_role / "
        f"legacy_primary_role / legacy_role_filter). Нарушители: {offenders}"
    )
