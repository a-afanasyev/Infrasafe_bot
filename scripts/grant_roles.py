#!/usr/bin/env python3
"""
Скрипт назначения всех ролей (applicant, executor, manager) пользователю по telegram_id.
Запуск:
  ./uk_management_bot/venv/bin/python scripts/grant_roles.py 48617336
"""
import sys
import json
import os

try:
    from uk_management_bot.database.session import SessionLocal
    from uk_management_bot.database.models.user import User
except ModuleNotFoundError:
    # Добавляем пути и пробуем относительный импорт из пакета
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
    PKG_DIR = os.path.join(PROJECT_ROOT, "uk_management_bot")
    if PKG_DIR not in sys.path:
        sys.path.insert(0, PKG_DIR)
    if PROJECT_ROOT not in sys.path:
        sys.path.insert(0, PROJECT_ROOT)
    from database.session import SessionLocal
    from database.models.user import User

ALL_ROLES = ["applicant", "executor", "manager"]


def main():
    if len(sys.argv) < 2:
        print("Usage: grant_roles.py <telegram_id>")
        sys.exit(1)
    try:
        telegram_id = int(sys.argv[1])
    except ValueError:
        print("telegram_id must be integer")
        sys.exit(1)

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.telegram_id == telegram_id).first()
        created = False
        if not user:
            user = User(
                telegram_id=telegram_id,
                username=None,
                first_name=None,
                last_name=None,
                language="ru",
                status="approved",
                role="manager",
                roles=json.dumps(ALL_ROLES, ensure_ascii=False),
                active_role="manager",
            )
            db.add(user)
            created = True
        else:
            # Обновляем статус и роли
            user.status = "approved"
            # Историческое поле role ставим в manager для совместимости с legacy-проверками
            user.role = "manager"
            # Обновляем JSON ролей, объединяя с текущими
            try:
                existing = json.loads(user.roles) if user.roles else []
                if not isinstance(existing, list):
                    existing = []
            except Exception:
                existing = []
            merged = sorted(list({*(r for r in existing if isinstance(r, str)), *ALL_ROLES}))
            user.roles = json.dumps(merged, ensure_ascii=False)
            if not user.active_role or user.active_role not in merged:
                user.active_role = "manager"
        db.commit()
        db.refresh(user)
        print(
            json.dumps(
                {
                    "ok": True,
                    "created": created,
                    "user": {
                        "id": user.id,
                        "telegram_id": user.telegram_id,
                        "status": user.status,
                        "role": user.role,
                        "roles": user.roles,
                        "active_role": user.active_role,
                    },
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    except Exception as e:
        db.rollback()
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
        sys.exit(2)
    finally:
        db.close()


if __name__ == "__main__":
    main()


