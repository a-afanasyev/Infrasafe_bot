#!/usr/bin/env python3
"""AUD5-PRAC-8: снапшот OpenAPI-схемы в репозиторий + diff-гейт.

`api/main.py` осознанно выключает интерактивные доки в проде (`docs_url=None`,
`redoc_url=None`, `openapi_url=None`) — публичная схема увеличивает поверхность
для скрейпа. Комментарий там же обещает: «ops gets schemas via repo». Обещание не
исполнялось: снапшота в репозитории не было, то есть схему негде было взять
вообще, и любое изменение контракта проходило без следа в диффе.

Здесь схема генерируется из того же `app.openapi()` и пишется в
`docs/tech/openapi.json`. В CI шаг перегенерирует файл и падает, если он
отличается от закоммиченного, — тогда изменение публичного контракта видно в
ревью как отдельный дифф, а не обнаруживается потребителем в проде.

Запуск:
    python3 scripts/dump_openapi.py            # перезаписать снапшот
    python3 scripts/dump_openapi.py --check    # сверить, не перезаписывая

Детерминированность: `sort_keys=True` + фиксированный отступ + перевод строки в
конце. Без этого дифф шумел бы на каждом прогоне из-за порядка ключей.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT = ROOT / "docs/tech/openapi.json"


def build_schema() -> dict:
    # DEBUG=true обязателен: при DEBUG=false схема собирается тем же
    # `app.openapi()`, но эагерная prod-валидация settings требует реальных
    # секретов. Снапшот от этого не зависит — набор роутов одинаков.
    os.environ.setdefault("DEBUG", "true")
    os.environ.setdefault("BOT_TOKEN", "dump:dummy-token")
    os.environ.setdefault("JWT_SECRET", "dump-dummy-secret")
    os.environ.setdefault("INVITE_SECRET", "dump-dummy-secret-2")
    os.environ.setdefault("ADMIN_PASSWORD", "dump-dummy-admin-pw-0123456")
    # URL нужен postgres-образный, но подключения не будет: `create_engine`
    # ленив, а схема собирается из роутов. sqlite здесь не годится —
    # `database/session.py` передаёт `max_overflow`/`pool_timeout`, которых
    # SingletonThreadPool sqlite не принимает, и импорт падает TypeError.
    os.environ.setdefault(
        "DATABASE_URL", "postgresql://openapi:dump@127.0.0.1:5432/openapi_dump"
    )
    sys.path.insert(0, str(ROOT))

    from uk_management_bot.api.main import app  # noqa: E402  (после настройки env)

    return app.openapi()


def render(schema: dict) -> str:
    return json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="сверить снапшот с текущей схемой, ничего не писать")
    args = ap.parse_args()

    current = render(build_schema())

    if args.check:
        if not SNAPSHOT.exists():
            print(f"✖ снапшота нет: {SNAPSHOT.relative_to(ROOT)}", file=sys.stderr)
            return 1
        if SNAPSHOT.read_text(encoding="utf-8") != current:
            print(
                "✖ OpenAPI-снапшот разошёлся с кодом. Публичный контракт API\n"
                "  изменился — это должно быть видно в диффе PR. Перегенерировать:\n"
                "      python3 scripts/dump_openapi.py",
                file=sys.stderr,
            )
            return 1
        print("✓ OpenAPI-снапшот совпадает с кодом")
        return 0

    SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT.write_text(current, encoding="utf-8")
    print(f"записан {SNAPSHOT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
