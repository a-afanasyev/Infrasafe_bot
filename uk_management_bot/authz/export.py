"""Выгрузка каталога действий для фронтенда.

Фронт показывает разделы и кнопки по списку `actions` из профиля и сверяет
ключи действий со сгенерированной копией каталога — так опечатка в ключе ловится
тестом, а не тихо прячет кнопку. Копия лежит в frontend/src/authz и обновляется
командой:

    python -m uk_management_bot.authz.export --write

Тест tests/services/test_authz_catalog.py падает, если копия устарела.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from uk_management_bot.authz.catalog import ACTIONS

FRONTEND_COPY = Path(__file__).resolve().parents[2] / "frontend" / "src" / "authz" / "catalog.generated.json"


def catalog_payload() -> dict:
    """Каталог в стабильном виде: ключ → роли по умолчанию, признаки, описание."""
    return {
        "_comment": "Сгенерировано: python -m uk_management_bot.authz.export --write. Не править руками.",
        "actions": {
            key: {
                "roles": sorted(action.default_roles),
                "approved_only": action.approved_only,
                "superadmin_only": action.superadmin_only,
                "title": action.title,
            }
            for key, action in sorted(ACTIONS.items())
        },
    }


def render() -> str:
    return json.dumps(catalog_payload(), ensure_ascii=False, indent=2) + "\n"


def render_markdown() -> str:
    """Таблица каталога для docs/tech/RBAC.md (раздел «Каталог действий»)."""
    lines = [
        "| Действие | Роли | Только одобренный | Что разрешает |",
        "|---|---|:-:|---|",
    ]
    for key, action in sorted(ACTIONS.items()):
        roles = ", ".join(f"`{r}`" for r in sorted(action.default_roles)) or "суперадмин"
        approved = "да" if action.approved_only else ""
        lines.append(f"| `{key}` | {roles} | {approved} | {action.title} |")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Выгрузка каталога действий RBAC для фронтенда")
    parser.add_argument("--write", action="store_true", help="перезаписать копию во фронтенде")
    parser.add_argument("--markdown", action="store_true", help="таблица каталога для docs/tech/RBAC.md")
    args = parser.parse_args()
    if args.markdown:
        print(render_markdown(), end="")
        return 0
    if args.write:
        FRONTEND_COPY.parent.mkdir(parents=True, exist_ok=True)
        FRONTEND_COPY.write_text(render(), encoding="utf-8")
        print(f"записан {FRONTEND_COPY}")
        return 0
    print(render(), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
