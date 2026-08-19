"""Житель мог написать комментарий в ЛЮБУЮ чужую заявку (секревью 2026-08-18).

Цепочка комментариев авторизовалась РОВНО ОДИН РАЗ — на входе
`handle_add_comment_start` (`has_request_access_sync`). Дальше номер заявки жил
в РАЗДЕЛЯЕМОМ ключе состояния `request_number`, а `handle_comment_confirmation`
не фильтрован по FSM-состоянию и права не перепроверял: `_apply_comment`
проверял только существование заявки и автора.

Примитив подмены — живой `return_request_<любой номер>`
(`handlers/request_acceptance.py`): он кладёт номер из клиентского callback_data
в тот же общий ключ БЕЗ проверки владения. Для своего потока это безопасно
(канонический `APPLICANT_RETURN` авторизует только владельца), но между шагами
чужой цепочки — это подмена цели.

Сценарий: начать комментарий к СВОЕЙ заявке → `return_request_<чужой номер>` →
`confirm_comment`. Комментарий коммитился в чужую заявку, попадал в аудит-лог и
РАССЫЛАЛСЯ уведомлениями заявителю и менеджерам как легитимный.

Чинится двумя независимыми слоями, каждый закрывает дыру сам по себе:
1. именованный ключ `comment_request_number` — примитив перестаёт достигать цели;
2. проверка доступа в самой точке ЗАПИСИ (`_apply_comment`) — цепочка больше не
   полагается на «нас авторизовали на входе».

Тем же заходом закрыты два чтения без проверки прав: `back_to_comments_`
(живое) и `view_comments_by_type_` (недостижимо из-за перекрытия префиксом,
но функция-загрузчик общая).
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from uk_management_bot.database.session import Base
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.user import User
from uk_management_bot.handlers import request_comments as rc
from uk_management_bot.services.comment_service import CommentService


OWNER_TG = 5001
STRANGER_TG = 5002


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def world(db):
    owner = User(id=1, telegram_id=OWNER_TG, username="owner", first_name="Хозяин",
                 roles='["applicant"]', active_role="applicant", status="approved", language="ru")
    stranger = User(id=2, telegram_id=STRANGER_TG, username="stranger", first_name="Посторонний",
                    roles='["applicant"]', active_role="applicant", status="approved", language="ru")
    db.add_all([owner, stranger])
    db.commit()

    victim = Request(request_number="260818-001", user_id=owner.id, category="Электрика",
                     address="Дом 1", description="Заявка владельца", status="Новая")
    own = Request(request_number="260818-002", user_id=stranger.id, category="Электрика",
                  address="Дом 2", description="Заявка постороннего", status="Новая")
    db.add_all([victim, own])
    db.commit()
    return {"owner": owner, "stranger": stranger, "victim": victim, "own": own}


class _FakeState:
    def __init__(self, **data):
        self._data = dict(data)
        self.state = None
        self.cleared = False

    async def get_data(self):
        return dict(self._data)

    async def update_data(self, **kwargs):
        self._data.update(kwargs)
        return dict(self._data)

    async def set_state(self, state):
        self.state = state

    async def clear(self):
        self.cleared = True
        self._data = {}


def _callback(data: str, from_id: int):
    cb = MagicMock()
    cb.data = data
    cb.from_user.id = from_id
    cb.answer = AsyncMock()
    cb.message.edit_text = AsyncMock()
    return cb


def _comment_count(db, request_number: str) -> int:
    return len(CommentService(db).get_request_comments(request_number, limit=100))


# ══════════════════════════════════════════════════════════════════════════════
# Точка ЗАПИСИ авторизует сама
# ══════════════════════════════════════════════════════════════════════════════

def test_apply_comment_rejects_foreign_request(db, world):
    """Слой 2: даже с «правильным» номером в состоянии запись запрещена."""
    verdict, _notices = rc._apply_comment(
        db, "260818-001", STRANGER_TG, "текст постороннего", "clarification"
    )

    assert verdict == "no_access"
    assert _comment_count(db, "260818-001") == 0


def test_apply_comment_allows_owner(db, world):
    verdict, _notices = rc._apply_comment(db, "260818-001", OWNER_TG, "текст владельца", "clarification")

    assert verdict == "ok"
    assert _comment_count(db, "260818-001") == 1


# ══════════════════════════════════════════════════════════════════════════════
# Полная цепочка эксплуатации не пишет ничего
# ══════════════════════════════════════════════════════════════════════════════

def test_exploit_chain_writes_nothing(db, world):
    """Слой 1: подменённый общий ключ до цепочки комментариев не доходит.

    Состояние ровно такое, каким его оставляет `return_request_<чужой номер>`:
    общий `request_number` — чужой, поля комментария — от легитимного шага.
    """
    state = _FakeState(
        request_number="260818-001",          # подменено через return_request_
        comment_request_number="260818-002",  # своё, поставленное цепочкой
        comment_type="clarification",
        comment_text="внедрённый текст",
    )
    callback = _callback("confirm_comment", STRANGER_TG)

    asyncio.run(rc.handle_comment_confirmation(callback, state, language="ru", _db=db))

    assert _comment_count(db, "260818-001") == 0, "комментарий уехал в чужую заявку"


def test_confirmation_without_own_key_does_not_fall_back(db, world):
    """Общий `request_number` НЕ должен подхватываться как запасной вариант."""
    state = _FakeState(
        request_number="260818-001",
        comment_type="clarification",
        comment_text="внедрённый текст",
    )
    callback = _callback("confirm_comment", STRANGER_TG)

    asyncio.run(rc.handle_comment_confirmation(callback, state, language="ru", _db=db))

    assert _comment_count(db, "260818-001") == 0
    callback.answer.assert_awaited()


def test_confirmation_writes_own_request(db, world):
    state = _FakeState(
        comment_request_number="260818-002",
        comment_type="clarification",
        comment_text="законный комментарий",
    )
    callback = _callback("confirm_comment", STRANGER_TG)

    asyncio.run(rc.handle_comment_confirmation(callback, state, language="ru", _db=db))

    assert _comment_count(db, "260818-002") == 1


# ══════════════════════════════════════════════════════════════════════════════
# Чтение истории тоже под правами
# ══════════════════════════════════════════════════════════════════════════════

def test_back_to_comments_denies_stranger(db, world):
    CommentService(db).add_comment(
        request_id="260818-001", user_id=1, comment_text="приватная переписка",
        comment_type="clarification",
    )
    callback = _callback("back_to_comments_260818-001", STRANGER_TG)

    asyncio.run(rc.handle_back_to_comments(callback, _FakeState(), language="ru", _db=db))

    callback.message.edit_text.assert_not_awaited()
    callback.answer.assert_awaited()


def test_back_to_comments_allows_owner(db, world):
    CommentService(db).add_comment(
        request_id="260818-001", user_id=1, comment_text="приватная переписка",
        comment_type="clarification",
    )
    callback = _callback("back_to_comments_260818-001", OWNER_TG)

    asyncio.run(rc.handle_back_to_comments(callback, _FakeState(), language="ru", _db=db))

    callback.message.edit_text.assert_awaited_once()


def test_comments_by_type_loader_checks_access(db, world):
    """Хендлер недостижим (перекрыт префиксом), но загрузчик обязан проверять."""
    CommentService(db).add_comment(
        request_id="260818-001", user_id=1, comment_text="приватная переписка",
        comment_type="clarification",
    )

    verdict, _ = rc._load_comments_by_type_view(
        db, "260818-001", "clarification", STRANGER_TG, "ru"
    )

    assert verdict == "no_access"


# ══════════════════════════════════════════════════════════════════════════════
# Ратчет: цепочка комментариев не читает разделяемый ключ
# ══════════════════════════════════════════════════════════════════════════════

def test_flow_driving_handlers_are_state_filtered():
    """Шаги цепочки не должны срабатывать из ЧУЖОГО состояния.

    Поведенческие тесты выше зовут функции напрямую и фильтры не проверяют —
    поэтому третий слой защиты фиксируется здесь, по декоратору. Без фильтра
    `confirm_comment` исполняется в состоянии любого другого флоу, а именно так
    и выглядела эксплуатация: `return_request_` переводил FSM в своё состояние,
    и это ничему не мешало.
    """
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(rc))
    want = {
        "handle_comment_confirmation": "waiting_for_confirmation",
        "handle_comment_type_selection": "waiting_for_comment_type",
    }
    missing = []
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name not in want:
            continue
        deco_src = " ".join(ast.unparse(d) for d in node.decorator_list)
        if want[node.name] not in deco_src:
            missing.append(node.name)

    assert not missing, f"хендлеры без фильтра по состоянию: {missing}"


def test_comment_chain_uses_namespaced_state_key():
    """Общий `request_number` в этом модуле запрещён.

    Именно он делал возможной подмену цели между шагами: любой хендлер любого
    другого флоу, пишущий в этот ключ, управлял целью нашей записи.
    """
    import inspect

    source = inspect.getsource(rc)
    offenders = [
        line.strip()
        for line in source.splitlines()
        if '"request_number"' in line and "comment_request_number" not in line
        and ("get_data" in line or "get(" in line or "update_data" in line)
    ]

    assert not offenders, f"цепочка читает/пишет разделяемый ключ: {offenders}"
