"""ARC-06 PR2 SSOT-гейт: инлайн user-by-id/telegram_id lookup запрещён.

Мигрированные файлы должны запрашивать пользователя по id/telegram_id ТОЛЬКО
через `api/users/queries.py` (get_/require_user_by_*), а не инлайн
`select(User).where(User.id == ...)` / `select(User).where(User.telegram_id == ...)`.

AST-only (не regex — regex ловит комментарии/строки и пропускает многострочный
код): ищем Compare-узлы `User.id == ...` / `User.telegram_id == ...` (левый
операнд — атрибут КЛАССА `User`, оператор `Eq`). `User.email ==` НЕ банится
(login-by-email — не дублированный lookup). Инстансные `user.id ==` (строчная
`user`) и `UserApartment.user_id ==` не матчатся (получатель не `User`-класс).

Список файлов расширяется при будущем полном выносе auth/registration.
`api/users/queries.py` — SSOT-дом этих select'ов — НЕ сканируется.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

SCANNED_FILES = [
    ROOT / "uk_management_bot" / "api" / "auth" / "router.py",
    ROOT / "uk_management_bot" / "api" / "registration" / "router.py",
    ROOT / "uk_management_bot" / "api" / "dependencies.py",
]

BANNED_ATTRS = frozenset({"id", "telegram_id"})


def _is_user_class_attr(node: ast.expr) -> bool:
    """True для `User.id` / `User.telegram_id` (атрибут КЛАССА User, не инстанса)."""
    return (
        isinstance(node, ast.Attribute)
        and node.attr in BANNED_ATTRS
        and isinstance(node.value, ast.Name)
        and node.value.id == "User"
    )


def collect_inline_user_lookups(path: Path) -> list[tuple[str, int]]:
    """→ [(relname, lineno)] инлайн-сравнений User.id/telegram_id == ..."""
    hits: list[tuple[str, int]] = []
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare):
            continue
        # только простое равенство: `User.id == X`
        if len(node.ops) != 1 or not isinstance(node.ops[0], ast.Eq):
            continue
        if _is_user_class_attr(node.left) or any(_is_user_class_attr(c) for c in node.comparators):
            hits.append((path.name, node.lineno))
    return hits


def test_migrated_files_have_no_inline_user_lookup():
    all_hits: list[str] = []
    for path in SCANNED_FILES:
        assert path.exists(), f"missing scanned file: {path}"
        for name, lineno in collect_inline_user_lookups(path):
            all_hits.append(f"{name}:{lineno}")
    assert not all_hits, (
        "ARC-06: инлайн `User.id/telegram_id ==` — используйте "
        "api/users/queries.py (get_/require_user_by_*):\n  " + "\n  ".join(all_hits)
    )
