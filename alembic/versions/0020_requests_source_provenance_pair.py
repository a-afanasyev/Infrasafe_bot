"""A9-P3-14: провенанс Group Intake — оба поля или ни одного.

Частичный уникальный индекс 0019 (``uq_requests_source_message`` по
``(source_chat_id, source_message_id)`` WHERE ``source_message_id IS NOT
NULL``) держит «одно сообщение группы — одна заявка», только когда
``source_chat_id`` задан: NULL в уникальном индексе не равен другому NULL, и
строки с одним ``source_message_id`` при ``source_chat_id IS NULL`` проходят.
Писатели (Group Intake → ``save_request``) ставят оба поля вместе — CHECK
делает это инвариантом схемы.

Перед миграцией строк с половинным провенансом быть не должно (единственный
писатель ставит пару). При наличии таких строк миграция упадёт на ADD
CONSTRAINT — разбирать руками, не автоматически.

Revision ID: 020
Revises: 019
Create Date: 2026-09-23
"""
from typing import Sequence, Union

from alembic import op

revision: str = "020"
down_revision: Union[str, None] = "019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_CONSTRAINT = "ck_requests_source_provenance_pair"


def upgrade() -> None:
    op.create_check_constraint(
        _CONSTRAINT,
        "requests",
        "(source_message_id IS NULL) = (source_chat_id IS NULL)",
    )


def downgrade() -> None:
    op.drop_constraint(_CONSTRAINT, "requests", type_="check")
