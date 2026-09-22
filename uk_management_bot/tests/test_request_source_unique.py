"""AUD7-CODE-03: durable-идемпотентность заявки по исходному сообщению группы.

Redis-CAS (pending.store_candidate) закрывает гонку правка/подтверждение, но
переживает ли она рестарт Redis, истёкший TTL и повторную доставку апдейта —
нет. Инвариант в БД: на одно исходное сообщение (source_chat_id,
source_message_id) — не более одной заявки; частичный уникальный индекс не
трогает заявки без источника (бот, дашборд, TWA — source NULL).
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.user import User
from uk_management_bot.database.session import Base


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    session.add(User(id=1, telegram_id=1001, first_name="A", roles='["applicant"]', active_role="applicant", status="approved"))
    session.commit()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def _request(number, **source):
    return Request(request_number=number, user_id=1, category="plumbing", description="d", **source)


def test_second_request_for_same_group_message_is_rejected(db):
    db.add(_request("260918-001", source_chat_id=-100500, source_message_id=42))
    db.commit()

    db.add(_request("260918-002", source_chat_id=-100500, source_message_id=42))
    with pytest.raises(IntegrityError):
        db.commit()


def test_requests_without_source_are_not_limited(db):
    db.add(_request("260918-001"))
    db.add(_request("260918-002"))
    db.commit()  # NULL-источник не участвует в уникальности
    # Половинный провенанс (chat без message) с миграции 0020 запрещён CHECK'ом
    # ck_requests_source_provenance_pair — см. tests/services/test_requests_source_pair_check.py.


def test_same_message_id_in_different_chats_is_fine(db):
    db.add(_request("260918-001", source_chat_id=-100500, source_message_id=42))
    db.add(_request("260918-002", source_chat_id=-100501, source_message_id=42))
    db.commit()
