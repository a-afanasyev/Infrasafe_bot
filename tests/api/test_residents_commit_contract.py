"""Контракт `commit=False` у переиспользуемых мутаций (Т1).

Раздел «Жители» переиспользует чужие мутации (`services/addresses/core.py`,
`api/shifts/service.py`), но обязан класть в ОДНУ транзакцию мутацию + AuditLog
+ строку outbox. Проблема: эти функции коммитят сами и сами зовут
`enqueue_outbox` — прямой реюз дал бы и потерю атомарности, и двойные события.

Отсюда однозначный контракт:

  commit=True  (умолчание, путь бота) — поведение прежнее бит-в-бит:
               мутация → enqueue_outbox → commit → publish_realtime;
               возвращается сущность.

  commit=False (путь residents-core) — ТОЛЬКО мутация + flush. Функция НЕ
               коммитит, НЕ зовёт enqueue_outbox и НЕ публикует в Redis;
               возвращает `{entity, event, payload}`, а владелец транзакции
               (residents-core) сам решает, что с этим делать.

`event=None` — легальный случай: у смены статуса аккаунта события в `_ROUTING`
нет, и residents-core обязан НЕ звать `enqueue_outbox` (иначе ValueError).

Здесь проверяются обе ветки: что новый режим ничего не коммитит и не эмитит, и
что дефолтный путь бота не изменился.
"""
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.api.shifts import service as shifts_service
from uk_management_bot.database.models.apartment import Apartment
from uk_management_bot.database.models.building import Building
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.user_apartment import UserApartment
from uk_management_bot.database.models.yard import Yard
from uk_management_bot.services.addresses import core
from uk_management_bot.services.addresses.events import _ROUTING

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def binding(db_session: AsyncSession):
    """pending-привязка жителя к квартире + сам житель."""
    yard = Yard(name="Двор-К")
    db_session.add(yard)
    await db_session.flush()
    bld = Building(address="К-1", yard_id=yard.id)
    db_session.add(bld)
    await db_session.flush()
    apt = Apartment(building_id=bld.id, apartment_number="7")
    db_session.add(apt)
    # Ревьюер с id=1 (тесты ниже зовут approve/reject с reviewer_id=1):
    # с BUG-177 точка записи перепроверяет роль — ревьюер обязан быть менеджером.
    reviewer = User(id=1, telegram_id=9000, first_name="Менеджер",
                    roles='["manager"]', status="approved")
    db_session.add(reviewer)
    user = User(telegram_id=9001, first_name="Тест", roles='["applicant"]', status="pending")
    db_session.add(user)
    await db_session.flush()
    ua = UserApartment(user_id=user.id, apartment_id=apt.id, status="pending")
    db_session.add(ua)
    await db_session.commit()
    await db_session.refresh(ua)
    return ua


class TestRoutingTable:

    async def test_removed_event_is_routable(self):
        """`apartment_request.removed` обязан быть в _ROUTING.

        Без него `enqueue_outbox` падает ValueError — а residents-core зовёт
        его при отвязке квартиры менеджером.
        """
        assert "apartment_request.removed" in _ROUTING


class TestNoCommitMode:

    async def test_approve_does_not_commit(self, db_session: AsyncSession, binding):
        ua_id = binding.id  # после rollback объект expire'нется — id берём заранее
        result = await core.approve_apartment_request(
            db_session, user_apartment_id=ua_id, reviewer_id=1, commit=False,
        )
        assert result["entity"].status == "approved"
        assert result["event"] == "apartment_request.approved"
        assert isinstance(result["payload"], dict)

        # Транзакция ещё открыта: откат обязан вернуть прежний статус.
        await db_session.rollback()
        refreshed = await db_session.get(UserApartment, ua_id)
        assert refreshed.status == "pending"

    async def test_approve_does_not_enqueue_outbox(self, db_session: AsyncSession, binding):
        with patch(
            "uk_management_bot.services.addresses.core.enqueue_outbox", new=AsyncMock()
        ) as enqueue:
            await core.approve_apartment_request(
                db_session, user_apartment_id=binding.id, reviewer_id=1, commit=False,
            )
        enqueue.assert_not_awaited()

    async def test_approve_does_not_publish_realtime(self, db_session: AsyncSession, binding):
        with patch(
            "uk_management_bot.services.addresses.core.publish_realtime_after_commit",
            new=AsyncMock(),
        ) as publish:
            await core.approve_apartment_request(
                db_session, user_apartment_id=binding.id, reviewer_id=1, commit=False,
            )
        publish.assert_not_awaited()

    async def test_reject_returns_its_own_event(self, db_session: AsyncSession, binding):
        result = await core.reject_apartment_request(
            db_session, user_apartment_id=binding.id, reviewer_id=1,
            comment="нет документов", commit=False,
        )
        assert result["entity"].status == "rejected"
        assert result["event"] == "apartment_request.rejected"

    async def test_remove_returns_removed_event(self, db_session: AsyncSession, binding):
        """Отвязка в no-commit режиме объявляет НОВОЕ событие.

        В commit=True она событий не эмитит (parity с legacy) — здесь же
        событие нужно, чтобы дашборды увидели исчезновение привязки.
        """
        ua_id = binding.id
        result = await core.remove_user_from_apartment(
            db_session, user_apartment_id=ua_id, commit=False,
        )
        assert result["event"] == "apartment_request.removed"
        assert result["payload"]["id"] is not None

        await db_session.rollback()
        assert await db_session.get(UserApartment, ua_id) is not None

    async def test_set_user_status_has_no_event(self, db_session: AsyncSession, binding):
        """У смены статуса аккаунта события нет — и это легально."""
        user_id = binding.user_id
        user = await db_session.get(User, user_id)
        result = await shifts_service.set_user_status(
            db_session, user, "approved", commit=False,
        )
        assert result["event"] is None
        assert result["entity"].status == "approved"

        await db_session.rollback()
        refreshed = await db_session.get(User, user_id)
        assert refreshed.status == "pending"

    async def test_guards_still_fire_in_no_commit_mode(self, db_session: AsyncSession, binding):
        """Гейт «заявка уже обработана» не должен зависеть от режима коммита."""
        await core.approve_apartment_request(
            db_session, user_apartment_id=binding.id, reviewer_id=1, commit=False,
        )
        with pytest.raises(Exception):
            await core.approve_apartment_request(
                db_session, user_apartment_id=binding.id, reviewer_id=1, commit=False,
            )


class TestDefaultModeUnchanged:
    """Regression: путь бота (commit=True) обязан остаться прежним бит-в-бит."""

    async def test_approve_commits_and_returns_entity(self, db_session: AsyncSession, binding):
        ua_id = binding.id
        ua = await core.approve_apartment_request(
            db_session, user_apartment_id=ua_id, reviewer_id=1,
        )
        # Возвращается сущность, а НЕ dict нового контракта.
        assert isinstance(ua, UserApartment)
        assert ua.status == "approved"

        await db_session.rollback()  # коммит уже был — откатывать нечего
        refreshed = (await db_session.execute(
            select(UserApartment).where(UserApartment.id == ua_id)
        )).scalar_one()
        assert refreshed.status == "approved"

    async def test_approve_still_enqueues_and_publishes(self, db_session: AsyncSession, binding):
        with patch(
            "uk_management_bot.services.addresses.core.enqueue_outbox", new=AsyncMock()
        ) as enqueue, patch(
            "uk_management_bot.services.addresses.core.publish_realtime_after_commit",
            new=AsyncMock(),
        ) as publish:
            await core.approve_apartment_request(
                db_session, user_apartment_id=binding.id, reviewer_id=1,
            )
        enqueue.assert_awaited_once()
        publish.assert_awaited_once()

    async def test_remove_commits_and_emits_nothing(self, db_session: AsyncSession, binding):
        with patch(
            "uk_management_bot.services.addresses.core.enqueue_outbox", new=AsyncMock()
        ) as enqueue:
            result = await core.remove_user_from_apartment(
                db_session, user_apartment_id=binding.id,
            )
        assert result is None                      # прежний тип результата
        enqueue.assert_not_awaited()               # parity: событий не было и нет
        assert await db_session.get(UserApartment, binding.id) is None

    async def test_set_user_status_default_commits(self, db_session: AsyncSession, binding):
        user_id = binding.user_id
        user = await db_session.get(User, user_id)
        result = await shifts_service.set_user_status(db_session, user, "blocked")
        assert result is None                      # прежний тип результата
        await db_session.rollback()
        refreshed = (await db_session.execute(
            select(User).where(User.id == user_id)
        )).scalar_one()
        assert refreshed.status == "blocked"
