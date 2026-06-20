"""FS-04: нормализация requests.category к каноническим EN-ключам

Прод-данные requests.category хранились смешанно: бот писал EN-ключи
(``plumbing``), а web/API — RU-лейблы (``Сантехника``), из-за чего аналитика
«По категориям» двоила дольки, а модалка назначения/бот-архив показывали сырой
ключ. После FS-04 канон — EN-ключ на всех каналах записи (валидатор
``_validate_request_category`` нормализует вход через ``resolve_category_key``).
Эта миграция переписывает существующие RU-лейблы на канон-EN-ключи.

Идемпотентно и кросс-диалектно (sqlite+pg): обычный ``UPDATE ... WHERE
category = <RU>``; повторный прогон — no-op (RU-строк уже нет). Маппинг = legacy
RU-лейблы из ``CATEGORY_DEFINITIONS`` + ``CATEGORY_TO_SPECIALIZATION``.

Revision ID: 023
Revises: 022
Create Date: 2026-06-20
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "023"
down_revision: Union[str, None] = "022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Legacy RU-лейбл → канонический EN-ключ.
_RU_TO_KEY = {
    "Электрика": "electricity",
    "Сантехника": "plumbing",
    "Отопление": "heating",
    "Вентиляция": "ventilation",
    "Лифт": "elevator",
    "Уборка": "cleaning",
    "Благоустройство": "landscaping",
    "Безопасность": "security",
    "Охрана": "security",
    "Интернет/ТВ": "internet",
    "Интернет": "internet",
    "Другое": "other",
    "Ремонт": "repair",
}

# Обратное соответствие для downgrade (канон-ключ → один RU-лейбл).
_KEY_TO_RU = {
    "electricity": "Электрика",
    "plumbing": "Сантехника",
    "heating": "Отопление",
    "ventilation": "Вентиляция",
    "elevator": "Лифт",
    "cleaning": "Уборка",
    "landscaping": "Благоустройство",
    "security": "Безопасность",
    "internet": "Интернет/ТВ",
    "other": "Другое",
    "repair": "Ремонт",
}


def upgrade() -> None:
    bind = op.get_bind()
    stmt = sa.text("UPDATE requests SET category = :key WHERE category = :ru")
    for ru, key in _RU_TO_KEY.items():
        bind.execute(stmt, {"key": key, "ru": ru})


def downgrade() -> None:
    bind = op.get_bind()
    stmt = sa.text("UPDATE requests SET category = :ru WHERE category = :key")
    for key, ru in _KEY_TO_RU.items():
        bind.execute(stmt, {"ru": ru, "key": key})
