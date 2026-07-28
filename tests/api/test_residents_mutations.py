"""Мутации раздела «Жители» (PR-3): RBAC, ownership, инварианты, атомарность.

Что здесь важно и почему:

* **Т2** — `users.status` общий на все роли, поэтому блокировка «жителя, который
  ещё и исполнитель» отняла бы у него рабочий доступ. Такие аккаунты раздел
  блокировать отказывается (409), их место — раздел «Сотрудники».
* **Т3** — вложенные ресурсы проверяются на принадлежность: чужой `ua_id` даёт
  404, а не молча правит чужую привязку.
* **Т6** — инвариант основной квартиры: не более одной primary, а при наличии
  approved-привязок — ровно одна. Проверяется на ВСЕХ путях, меняющих состав.
* **Т13** — state machine: повторные и невозможные переходы дают 409, а не
  «успешно, но ничего не изменилось».
* **Атомарность** — сбой на AuditLog обязан откатить и саму мутацию; событие
  эмитится ровно один раз; падение уведомления не роняет запрос.
"""
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.api.dependencies import get_current_user
from uk_management_bot.api.main import app
from uk_management_bot.database.models.apartment import Apartment
from uk_management_bot.database.models.audit import AuditLog
from uk_management_bot.database.models.building import Building
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.user_apartment import UserApartment
from uk_management_bot.database.models.yard import Yard

pytestmark = pytest.mark.asyncio

BASE = "/api/v2/residents"


# ═══════════════════════ Fixtures ═══════════════════════


@pytest_asyncio.fixture(autouse=True)
def _mute_telegram():
    """Уведомления в Telegram глушим во всех тестах, кроме тех, что их проверяют."""
    with patch("uk_management_bot.api.residents.notify._send", new=AsyncMock()):
        yield


@pytest_asyncio.fixture
async def address(db_session: AsyncSession):
    yard = Yard(name="Двор-М")
    db_session.add(yard)
    await db_session.flush()
    bld = Building(address="М-1", yard_id=yard.id)
    db_session.add(bld)
    await db_session.flush()
    apts = [Apartment(building_id=bld.id, apartment_number=str(n)) for n in (1, 2, 3)]
    db_session.add_all(apts)
    await db_session.commit()
    for a in apts:
        await db_session.refresh(a)
    return apts


async def _resident(db, tg, *, roles='["applicant"]', status="pending") -> User:
    u = User(telegram_id=tg, first_name="Ж", last_name=str(tg), roles=roles,
             active_role="applicant", status=status, language="ru")
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


async def _bind(db, user_id, apartment_id, *, status="approved", is_primary=False):
    ua = UserApartment(user_id=user_id, apartment_id=apartment_id,
                       status=status, is_primary=is_primary)
    db.add(ua)
    await db.commit()
    await db.refresh(ua)
    return ua


async def _primaries(db, user_id) -> list[int]:
    # Мутации идут через СВОЮ сессию (override_get_db), поэтому identity map
    # этой сессии держит устаревшие объекты — без expire_all тест читал бы
    # состояние «до» и проходил бы вхолостую.
    db.expire_all()
    rows = (await db.execute(
        select(UserApartment).where(UserApartment.user_id == user_id)
    )).scalars().all()
    return [r.id for r in rows if r.is_primary]


# ═══════════════════════ RBAC ═══════════════════════


class TestRBAC:

    async def test_non_manager_forbidden(self, client: AsyncClient, db_session: AsyncSession):
        resident = await _resident(db_session, 4001)
        prev = app.dependency_overrides[get_current_user]
        app.dependency_overrides[get_current_user] = lambda: resident
        try:
            r = await client.post(f"{BASE}/{resident.id}/approve", json={})
            assert r.status_code == 403
        finally:
            app.dependency_overrides[get_current_user] = prev


# ═══════════════════════ Т13: state machine аккаунта ═══════════════════════


class TestAccountStateMachine:

    async def test_approve_pending(self, client: AsyncClient, db_session: AsyncSession):
        resident = await _resident(db_session, 4101, status="pending")
        r = await client.post(f"{BASE}/{resident.id}/approve", json={})
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "approved"

    async def test_repeat_approve_conflicts(self, client: AsyncClient, db_session: AsyncSession):
        resident = await _resident(db_session, 4102, status="approved")
        assert (await client.post(f"{BASE}/{resident.id}/approve", json={})).status_code == 409

    async def test_approve_blocked_conflicts(self, client: AsyncClient, db_session: AsyncSession):
        resident = await _resident(db_session, 4103, status="blocked")
        assert (await client.post(f"{BASE}/{resident.id}/approve", json={})).status_code == 409

    async def test_block_then_repeat_conflicts(self, client: AsyncClient, db_session: AsyncSession):
        resident = await _resident(db_session, 4104, status="approved")
        ok = await client.post(f"{BASE}/{resident.id}/block", json={"reason": "мошенничество"})
        assert ok.status_code == 200
        again = await client.post(f"{BASE}/{resident.id}/block", json={"reason": "мошенничество"})
        assert again.status_code == 409

    async def test_block_requires_reason(self, client: AsyncClient, db_session: AsyncSession):
        resident = await _resident(db_session, 4105, status="approved")
        assert (await client.post(f"{BASE}/{resident.id}/block", json={"reason": "ab"})).status_code == 422

    async def test_unblock_only_from_blocked(self, client: AsyncClient, db_session: AsyncSession):
        resident = await _resident(db_session, 4106, status="approved")
        assert (await client.post(f"{BASE}/{resident.id}/unblock")).status_code == 409

    async def test_unblock_restores_approved(self, client: AsyncClient, db_session: AsyncSession):
        resident = await _resident(db_session, 4107, status="blocked")
        r = await client.post(f"{BASE}/{resident.id}/unblock")
        assert r.status_code == 200
        assert r.json()["status"] == "approved"

    async def test_unknown_resident_404(self, client: AsyncClient):
        assert (await client.post(f"{BASE}/999999/approve", json={})).status_code == 404


# ═══════════════════════ Т2: блокировка мультиролевых ═══════════════════════


class TestBlockGuard:

    async def test_staff_role_blocks_the_block(self, client: AsyncClient, db_session: AsyncSession):
        resident = await _resident(db_session, 4201, roles='["applicant", "executor"]',
                                   status="approved")
        r = await client.post(f"{BASE}/{resident.id}/block", json={"reason": "проверка"})
        assert r.status_code == 409
        assert "Сотрудники" in r.json()["detail"]

    async def test_meter_entry_capability_is_not_staff(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """`resource_meter_entry` — капабилити жителя, а не рабочая роль."""
        resident = await _resident(db_session, 4202,
                                   roles='["applicant", "resource_meter_entry"]',
                                   status="approved")
        r = await client.post(f"{BASE}/{resident.id}/block", json={"reason": "проверка"})
        assert r.status_code == 200

    async def test_unblock_also_guarded(self, client: AsyncClient, db_session: AsyncSession):
        resident = await _resident(db_session, 4203, roles='["applicant", "manager"]',
                                   status="blocked")
        assert (await client.post(f"{BASE}/{resident.id}/unblock")).status_code == 409


# ═══════════════════════ Т3: ownership вложенных ресурсов ═══════════════════════


class TestOwnership:

    async def test_foreign_binding_is_404(
        self, client: AsyncClient, db_session: AsyncSession, address
    ):
        victim = await _resident(db_session, 4301, status="approved")
        attacker = await _resident(db_session, 4302, status="approved")
        ua = await _bind(db_session, victim.id, address[0].id)

        for method, url, body in (
            ("post", f"{BASE}/{attacker.id}/apartments/{ua.id}/approve", {}),
            ("post", f"{BASE}/{attacker.id}/apartments/{ua.id}/reject",
             {"comment": "чужая привязка"}),
            ("patch", f"{BASE}/{attacker.id}/apartments/{ua.id}", {}),
            ("delete", f"{BASE}/{attacker.id}/apartments/{ua.id}", None),
        ):
            r = await getattr(client, method)(url, **({"json": body} if body is not None else {}))
            assert r.status_code == 404, f"{method} {url} → {r.status_code}"

    async def test_binding_of_missing_resident_is_404(
        self, client: AsyncClient, db_session: AsyncSession, address
    ):
        assert (await client.delete(f"{BASE}/999999/apartments/1")).status_code == 404


# ═══════════════════════ Привязка квартиры менеджером ═══════════════════════


class TestAttach:

    async def test_attach_is_approved_immediately(
        self, client: AsyncClient, db_session: AsyncSession, address
    ):
        resident = await _resident(db_session, 4401, status="approved")
        r = await client.post(f"{BASE}/{resident.id}/apartments",
                              json={"apartment_id": address[0].id})
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["status"] == "approved"
        assert body["yard_name"] == "Двор-М"

    async def test_duplicate_binding_conflicts(
        self, client: AsyncClient, db_session: AsyncSession, address
    ):
        resident = await _resident(db_session, 4402, status="approved")
        await _bind(db_session, resident.id, address[0].id)
        r = await client.post(f"{BASE}/{resident.id}/apartments",
                              json={"apartment_id": address[0].id})
        assert r.status_code == 409

    async def test_inactive_apartment_conflicts(
        self, client: AsyncClient, db_session: AsyncSession, address
    ):
        address[0].is_active = False
        await db_session.commit()
        resident = await _resident(db_session, 4403, status="approved")
        r = await client.post(f"{BASE}/{resident.id}/apartments",
                              json={"apartment_id": address[0].id})
        assert r.status_code == 409

    async def test_previously_rejected_can_be_attached_again(
        self, client: AsyncClient, db_session: AsyncSession, address
    ):
        """Отказ менеджера обратим: иначе исправить свою же ошибку нечем."""
        resident = await _resident(db_session, 4406, status="approved")
        await _bind(db_session, resident.id, address[0].id, status="rejected")

        r = await client.post(f"{BASE}/{resident.id}/apartments",
                              json={"apartment_id": address[0].id})
        assert r.status_code == 201, r.text
        assert r.json()["status"] == "approved"
        assert r.json()["is_primary"] is True

    async def test_missing_apartment_404(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        resident = await _resident(db_session, 4404, status="approved")
        r = await client.post(f"{BASE}/{resident.id}/apartments", json={"apartment_id": 999999})
        assert r.status_code == 404

    async def test_unknown_body_field_rejected(
        self, client: AsyncClient, db_session: AsyncSession, address
    ):
        resident = await _resident(db_session, 4405, status="approved")
        r = await client.post(f"{BASE}/{resident.id}/apartments",
                              json={"apartment_id": address[0].id, "primary": True})
        assert r.status_code == 422


# ═══════════════════════ Т6: инвариант основной квартиры ═══════════════════════


class TestPrimaryInvariant:

    async def test_first_attach_becomes_primary_even_if_not_requested(
        self, client: AsyncClient, db_session: AsyncSession, address
    ):
        """Флаг клиента игнорируется: у жителя с квартирой обязан быть адрес."""
        resident = await _resident(db_session, 4501, status="approved")
        r = await client.post(f"{BASE}/{resident.id}/apartments",
                              json={"apartment_id": address[0].id, "is_primary": False})
        assert r.json()["is_primary"] is True

    async def test_two_attaches_leave_exactly_one_primary(
        self, client: AsyncClient, db_session: AsyncSession, address
    ):
        resident = await _resident(db_session, 4502, status="approved")
        await client.post(f"{BASE}/{resident.id}/apartments", json={"apartment_id": address[0].id})
        await client.post(f"{BASE}/{resident.id}/apartments",
                          json={"apartment_id": address[1].id, "is_primary": True})
        assert len(await _primaries(db_session, resident.id)) == 1

    async def test_set_primary_moves_the_flag(
        self, client: AsyncClient, db_session: AsyncSession, address
    ):
        resident = await _resident(db_session, 4503, status="approved")
        first = await _bind(db_session, resident.id, address[0].id, is_primary=True)
        second = await _bind(db_session, resident.id, address[1].id)

        r = await client.patch(f"{BASE}/{resident.id}/apartments/{second.id}",
                               json={"is_primary": True})
        assert r.status_code == 200
        assert await _primaries(db_session, resident.id) == [second.id]
        await db_session.refresh(first)
        assert first.is_primary is False

    async def test_cannot_drop_the_only_primary(
        self, client: AsyncClient, db_session: AsyncSession, address
    ):
        resident = await _resident(db_session, 4504, status="approved")
        only = await _bind(db_session, resident.id, address[0].id, is_primary=True)
        r = await client.patch(f"{BASE}/{resident.id}/apartments/{only.id}",
                               json={"is_primary": False})
        assert r.status_code == 409

    async def test_dropping_primary_promotes_the_oldest(
        self, client: AsyncClient, db_session: AsyncSession, address
    ):
        resident = await _resident(db_session, 4505, status="approved")
        old = await _bind(db_session, resident.id, address[0].id)
        newer = await _bind(db_session, resident.id, address[1].id, is_primary=True)

        r = await client.patch(f"{BASE}/{resident.id}/apartments/{newer.id}",
                               json={"is_primary": False})
        assert r.status_code == 200
        assert await _primaries(db_session, resident.id) == [old.id]

    async def test_dropping_primary_from_the_oldest_promotes_the_next(
        self, client: AsyncClient, db_session: AsyncSession, address
    ):
        """Снятие признака у САМОЙ СТАРОЙ обязано отдать его следующей.

        Найдено прод-проверкой: «самой старой approved» оказывалась та же
        привязка, у которой признак только что сняли, и запрос возвращал 200,
        не изменив ничего. Тест `test_dropping_primary_promotes_the_oldest`
        этого не ловил — там основной была НЕ самая старая.
        """
        resident = await _resident(db_session, 4510, status="approved")
        oldest = await _bind(db_session, resident.id, address[0].id, is_primary=True)
        newer = await _bind(db_session, resident.id, address[1].id)

        r = await client.patch(f"{BASE}/{resident.id}/apartments/{oldest.id}",
                               json={"is_primary": False})
        assert r.status_code == 200
        assert r.json()["is_primary"] is False
        assert await _primaries(db_session, resident.id) == [newer.id]

    async def test_removing_primary_promotes_survivor(
        self, client: AsyncClient, db_session: AsyncSession, address
    ):
        resident = await _resident(db_session, 4506, status="approved")
        primary = await _bind(db_session, resident.id, address[0].id, is_primary=True)
        survivor = await _bind(db_session, resident.id, address[1].id)

        assert (await client.delete(
            f"{BASE}/{resident.id}/apartments/{primary.id}")).status_code == 204
        assert await _primaries(db_session, resident.id) == [survivor.id]

    async def test_approving_pending_when_no_primary_yet(
        self, client: AsyncClient, db_session: AsyncSession, address
    ):
        resident = await _resident(db_session, 4507, status="approved")
        pending = await _bind(db_session, resident.id, address[0].id, status="pending")

        r = await client.post(f"{BASE}/{resident.id}/apartments/{pending.id}/approve", json={})
        assert r.status_code == 200
        assert r.json()["is_primary"] is True

    async def test_approving_second_does_not_steal_primary(
        self, client: AsyncClient, db_session: AsyncSession, address
    ):
        resident = await _resident(db_session, 4508, status="approved")
        existing = await _bind(db_session, resident.id, address[0].id, is_primary=True)
        pending = await _bind(db_session, resident.id, address[1].id, status="pending")

        r = await client.post(f"{BASE}/{resident.id}/apartments/{pending.id}/approve", json={})
        assert r.json()["is_primary"] is False
        assert await _primaries(db_session, resident.id) == [existing.id]

    async def test_rejecting_primary_releases_the_flag(
        self, client: AsyncClient, db_session: AsyncSession, address
    ):
        """Отклонённая привязка не может остаться основной."""
        resident = await _resident(db_session, 4509, status="approved")
        pending = await _bind(db_session, resident.id, address[0].id,
                              status="pending", is_primary=True)

        r = await client.post(f"{BASE}/{resident.id}/apartments/{pending.id}/reject",
                              json={"comment": "нет документов"})
        assert r.status_code == 200
        assert r.json()["is_primary"] is False
        assert await _primaries(db_session, resident.id) == []


# ═══════════════════════ Модерация привязок ═══════════════════════


class TestBindingModeration:

    async def test_reject_requires_comment(
        self, client: AsyncClient, db_session: AsyncSession, address
    ):
        resident = await _resident(db_session, 4601, status="approved")
        ua = await _bind(db_session, resident.id, address[0].id, status="pending")
        r = await client.post(f"{BASE}/{resident.id}/apartments/{ua.id}/reject",
                              json={"comment": "no"})
        assert r.status_code == 422

    async def test_approving_already_approved_conflicts(
        self, client: AsyncClient, db_session: AsyncSession, address
    ):
        resident = await _resident(db_session, 4602, status="approved")
        ua = await _bind(db_session, resident.id, address[0].id, status="approved")
        r = await client.post(f"{BASE}/{resident.id}/apartments/{ua.id}/approve", json={})
        assert r.status_code == 409

    async def test_owner_toggle(
        self, client: AsyncClient, db_session: AsyncSession, address
    ):
        resident = await _resident(db_session, 4603, status="approved")
        ua = await _bind(db_session, resident.id, address[0].id, is_primary=True)
        r = await client.patch(f"{BASE}/{resident.id}/apartments/{ua.id}",
                               json={"is_owner": True})
        assert r.status_code == 200
        assert r.json()["is_owner"] is True


# ═══════════════════════ Атомарность и события (Т1) ═══════════════════════


class TestAtomicity:

    async def test_audit_failure_rolls_back_the_status(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Сбой на AuditLog обязан откатить и саму мутацию."""
        resident = await _resident(db_session, 4701, status="pending")
        resident_id = resident.id  # после expire_all атрибуты потребовали бы sync-IO

        with patch(
            "uk_management_bot.services.residents.core._audit",
            side_effect=RuntimeError("audit down"),
        ):
            with pytest.raises(RuntimeError):
                await client.post(f"{BASE}/{resident.id}/approve", json={})

        db_session.expire_all()
        fresh = (await db_session.execute(
            select(User).where(User.id == resident_id)
        )).scalar_one()
        assert fresh.status == "pending"

    async def test_account_approve_does_not_enqueue_outbox(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """У статусов аккаунта события нет — enqueue_outbox звать НЕЛЬЗЯ.

        Он падает ValueError на неизвестном событии, и это правильно: иначе
        событие потерялось бы молча.
        """
        resident = await _resident(db_session, 4702, status="pending")
        with patch(
            "uk_management_bot.services.residents.core.enqueue_outbox", new=AsyncMock()
        ) as enqueue:
            r = await client.post(f"{BASE}/{resident.id}/approve", json={})
        assert r.status_code == 200
        enqueue.assert_not_awaited()

    async def test_attach_emits_exactly_one_event(
        self, client: AsyncClient, db_session: AsyncSession, address
    ):
        resident = await _resident(db_session, 4703, status="approved")
        with patch(
            "uk_management_bot.services.residents.core.enqueue_outbox", new=AsyncMock()
        ) as enqueue, patch(
            "uk_management_bot.services.residents.core.publish_realtime_after_commit",
            new=AsyncMock(),
        ) as publish:
            r = await client.post(f"{BASE}/{resident.id}/apartments",
                                  json={"apartment_id": address[0].id})
        assert r.status_code == 201
        enqueue.assert_awaited_once()
        publish.assert_awaited_once()

    async def test_remove_emits_removed_event(
        self, client: AsyncClient, db_session: AsyncSession, address
    ):
        resident = await _resident(db_session, 4704, status="approved")
        ua = await _bind(db_session, resident.id, address[0].id, is_primary=True)
        with patch(
            "uk_management_bot.services.residents.core.publish_realtime_after_commit",
            new=AsyncMock(),
        ) as publish:
            r = await client.delete(f"{BASE}/{resident.id}/apartments/{ua.id}")
        assert r.status_code == 204
        publish.assert_awaited_once()
        assert publish.await_args.args[0] == "apartment_request.removed"

    async def test_audit_row_uses_bot_action_literals(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        resident = await _resident(db_session, 4705, status="pending")
        await client.post(f"{BASE}/{resident.id}/approve", json={})

        actions = (await db_session.execute(select(AuditLog.action))).scalars().all()
        assert "user_approved" in actions


# ═══════════════════════ Уведомления (Т11) ═══════════════════════


class TestNotifications:

    async def test_approve_sends_message_with_restart_button(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        resident = await _resident(db_session, 4801, status="pending")
        with patch("uk_management_bot.api.residents.notify._send", new=AsyncMock()) as send:
            r = await client.post(f"{BASE}/{resident.id}/approve", json={})
        assert r.status_code == 200
        send.assert_awaited_once()
        _chat_id, _text, markup = send.await_args.args
        assert markup["inline_keyboard"][0][0]["callback_data"] == "restart_bot"

    async def test_block_sends_nothing(self, client: AsyncClient, db_session: AsyncSession):
        """Parity с ботом: о блокировке житель отдельным сообщением не узнаёт."""
        resident = await _resident(db_session, 4802, status="approved")
        with patch("uk_management_bot.api.residents.notify._send", new=AsyncMock()) as send:
            await client.post(f"{BASE}/{resident.id}/block", json={"reason": "проверка"})
        send.assert_not_awaited()

    async def test_telegram_failure_does_not_fail_the_request(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Решение менеджера уже в БД — недоступный Telegram не делает из этого 500."""
        resident = await _resident(db_session, 4803, status="pending")
        resident_id = resident.id
        with patch(
            "uk_management_bot.api.residents.notify._send",
            side_effect=RuntimeError("telegram down"),
        ):
            r = await client.post(f"{BASE}/{resident.id}/approve", json={})
        assert r.status_code == 200

        db_session.expire_all()
        fresh = (await db_session.execute(
            select(User).where(User.id == resident_id)
        )).scalar_one()
        assert fresh.status == "approved"

    async def test_reject_notification_carries_reason(
        self, client: AsyncClient, db_session: AsyncSession, address
    ):
        resident = await _resident(db_session, 4804, status="approved")
        ua = await _bind(db_session, resident.id, address[0].id, status="pending")
        with patch("uk_management_bot.api.residents.notify._send", new=AsyncMock()) as send:
            await client.post(f"{BASE}/{resident.id}/apartments/{ua.id}/reject",
                              json={"comment": "нет документов"})
        _chat_id, text, _markup = send.await_args.args
        assert "нет документов" in text
        assert "Двор-М" in text
