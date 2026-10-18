"""Документы жителя — зашифрованно в медиа-сервисе; ключ в строке.

``user_documents`` получает зашифрованную тройку ``media_id`` (UNIQUE) +
``encryption_key`` + ``document_uuid``; ``file_id`` становится nullable.
XOR-инвариант: строка — либо легаси (непустой Telegram ``file_id``), либо
полная тройка; ни пустой, ни смешанной.

Инвариант «документы живут, пока проверка открыта» (`verification_status` ∈
{pending, requested} и `deleted_at IS NULL`) приложение держит само — оно
удаляет строки до commit решения, чтобы собрать `media_id` для гигиены.
Триггер на `users` — страховка для забытых/будущих путей: удаляет документы,
как только проверка закрылась. Удаление строки = уничтожение ключа.

Downgrade после первых зашифрованных загрузок запрещён: `file_id NOT NULL`
не вернуть, а blob'ы без ключей стали бы неразыскиваемыми.

Revision ID: 026
Revises: 025
Create Date: 2026-10-18
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "026"
down_revision: Union[str, None] = "025"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

STORAGE_XOR = (
    "(file_id IS NOT NULL AND file_id <> '' AND media_id IS NULL"
    " AND encryption_key IS NULL AND document_uuid IS NULL)"
    " OR (file_id IS NULL AND media_id IS NOT NULL"
    " AND encryption_key IS NOT NULL AND document_uuid IS NOT NULL)"
)

PURGE_FN = r"""
CREATE OR REPLACE FUNCTION purge_closed_verification_documents() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.verification_status NOT IN ('pending', 'requested') OR NEW.deleted_at IS NOT NULL THEN
        DELETE FROM user_documents WHERE user_id = NEW.id;
    END IF;
    RETURN NEW;
END;
$$
"""

PURGE_TRIGGER = """
CREATE TRIGGER trg_users_purge_closed_verification_documents
AFTER UPDATE OF verification_status, deleted_at ON users
FOR EACH ROW EXECUTE FUNCTION purge_closed_verification_documents()
"""


def upgrade() -> None:
    op.alter_column("user_documents", "file_id", existing_type=sa.String(255), nullable=True)
    op.add_column("user_documents", sa.Column("media_id", sa.Integer(), nullable=True))
    op.add_column("user_documents", sa.Column("encryption_key", sa.LargeBinary(), nullable=True))
    op.add_column("user_documents", sa.Column("document_uuid", sa.String(36), nullable=True))
    op.create_unique_constraint("uq_user_documents_media_id", "user_documents", ["media_id"])
    op.create_check_constraint("ck_user_documents_storage_xor", "user_documents", STORAGE_XOR)
    op.execute(PURGE_FN)
    op.execute(PURGE_TRIGGER)


def downgrade() -> None:
    encrypted = op.get_bind().execute(
        sa.text("SELECT count(*) FROM user_documents WHERE media_id IS NOT NULL")
    ).scalar()
    if encrypted:
        raise RuntimeError(
            f"026 downgrade запрещён: {encrypted} зашифрованных документов — "
            "file_id NOT NULL не вернуть, ключи были бы потеряны"
        )
    op.execute("DROP TRIGGER IF EXISTS trg_users_purge_closed_verification_documents ON users")
    op.execute("DROP FUNCTION IF EXISTS purge_closed_verification_documents()")
    op.drop_constraint("ck_user_documents_storage_xor", "user_documents", type_="check")
    op.drop_constraint("uq_user_documents_media_id", "user_documents", type_="unique")
    op.drop_column("user_documents", "document_uuid")
    op.drop_column("user_documents", "encryption_key")
    op.drop_column("user_documents", "media_id")
    op.alter_column("user_documents", "file_id", existing_type=sa.String(255), nullable=False)
