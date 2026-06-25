#!/usr/bin/env python3
"""TEST-071: seed (or update) a manager user for the Playwright e2e login flow.

Идемпотентно создаёт/обновляет пользователя-менеджера с email + паролем, чтобы
тест `tests/e2e/specs/login-flow.spec.ts::successful login redirects` перестал
скипаться.

⚠️ Login требует MFA (Telegram OTP) — после валидного пароля бэкенд шлёт код в
Telegram. Поэтому `telegram_id` ДОЛЖЕН быть реальным чатом, который уже запустил
бота (например, ваш личный аккаунт или QA-аккаунт), иначе OTP не дойдёт и тест
увидит 503. Тест засчитывает как успех и попадание на /uk/dashboard, и появление
шага ввода OTP («Код отправлен»).

Запуск (внутри контейнера или через venv):
  docker exec uk-management-bot python scripts/seed_e2e_user.py \
      --email admin@test.com --password 'E2eTest!2026' --telegram-id 6055402868

Параметры читаются также из env (CLI приоритетнее):
  E2E_MANAGER_EMAIL / E2E_MANAGER_PASSWORD / E2E_MANAGER_TELEGRAM_ID

После сидинга пропишите те же email/пароль в tests/e2e/.env (см. .env.example).
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import bcrypt

try:
    from uk_management_bot.database.session import SessionLocal
    from uk_management_bot.database.models.user import User
except ModuleNotFoundError:
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
    PKG_DIR = os.path.join(PROJECT_ROOT, "uk_management_bot")
    for p in (PKG_DIR, PROJECT_ROOT):
        if p not in sys.path:
            sys.path.insert(0, p)
    from database.session import SessionLocal
    from database.models.user import User


def _hash_password(password: str) -> str:
    # Mirror api/auth/service.hash_password (bcrypt) so login's verify_password matches.
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def _ensure_manager_roles(raw: str | None) -> str:
    roles: list[str] = []
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                roles = [str(r) for r in parsed]
        except (ValueError, TypeError):
            roles = []
    if "manager" not in roles:
        roles.append("manager")
    return json.dumps(roles)


def _resolve_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed an e2e manager user.")
    parser.add_argument("--email", default=os.getenv("E2E_MANAGER_EMAIL", "admin@test.com"))
    parser.add_argument("--password", default=os.getenv("E2E_MANAGER_PASSWORD"))
    parser.add_argument(
        "--telegram-id",
        type=int,
        default=int(os.getenv("E2E_MANAGER_TELEGRAM_ID", "0")) or None,
    )
    return parser.parse_args()


def main() -> int:
    args = _resolve_args()
    if not args.password:
        print("ERROR: password required (--password or E2E_MANAGER_PASSWORD)", file=sys.stderr)
        return 2
    if not args.telegram_id:
        print(
            "ERROR: telegram_id required (--telegram-id or E2E_MANAGER_TELEGRAM_ID) — "
            "must be a real chat that started the bot (MFA OTP target)",
            file=sys.stderr,
        )
        return 2

    db = SessionLocal()
    try:
        # Authoritative match by telegram_id (OTP target); fall back to email.
        user = db.query(User).filter(User.telegram_id == args.telegram_id).first()
        if user is None:
            user = db.query(User).filter(User.email == args.email).first()

        action = "updated"
        if user is None:
            user = User(telegram_id=args.telegram_id)
            db.add(user)
            action = "created"

        user.telegram_id = args.telegram_id
        user.email = args.email
        user.password_hash = _hash_password(args.password)
        user.roles = _ensure_manager_roles(user.roles)
        user.active_role = "manager"
        user.status = "approved"
        if not user.first_name:
            user.first_name = "E2E"
        if not user.last_name:
            user.last_name = "Manager"

        db.commit()
        print(
            f"OK: {action} e2e manager — id={user.id} telegram_id={user.telegram_id} "
            f"email={user.email} roles={user.roles} status={user.status}"
        )
        return 0
    except Exception as e:  # surface DB/constraint errors clearly
        db.rollback()
        print(f"ERROR: seeding failed: {e}", file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
