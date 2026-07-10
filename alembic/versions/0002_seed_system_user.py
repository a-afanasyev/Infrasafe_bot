"""PRC-05 companion: seed InfraSafe system user (было в миграции 009).

Системный юзер держит авто-заявки (InfraSafe-вебхуки, FIX-007): человека-владельца
нет. Хендлер резолвит его по sentinel telegram_id = settings.
INFRASAFE_SYSTEM_USER_TELEGRAM_ID (default 0). На ОБОИХ живых продах системный
юзер = telegram_id 0 (env unset) — проверено. Константа зафиксирована здесь (НЕ
читаем env В миграции — детерминизм fresh-install).

Идемпотентно: ON CONFLICT (telegram_id) DO NOTHING (users.telegram_id UNIQUE).
На прод пере-штампе (B6) 002 НЕ выполняется (штамп сразу в 002) — сид только для
fresh-install; на существующих продах юзер уже есть.

Revision ID: 002
Revises: 001
Create Date: 2026-07-10
"""
from typing import Sequence, Union

from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Валидируется CI-тестом против settings.INFRASAFE_SYSTEM_USER_TELEGRAM_ID.
SYSTEM_TELEGRAM_ID = 0


def upgrade() -> None:
    op.execute(
        f"""
        INSERT INTO users
            (telegram_id, first_name, roles, active_role, status, language, verification_status)
        VALUES
            ({SYSTEM_TELEGRAM_ID}, 'InfraSafe', '["manager"]', 'manager', 'approved', 'ru', 'verified')
        ON CONFLICT (telegram_id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute(f"DELETE FROM users WHERE telegram_id = {SYSTEM_TELEGRAM_ID}")
