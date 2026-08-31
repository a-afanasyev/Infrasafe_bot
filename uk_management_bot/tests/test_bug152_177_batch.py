"""BUG-152 (пп.3–5) + BUG-177 — волна A2, батч 2.

  * language пробрасывается в клавиатуры модерации/выбора квартиры и
    типа документа (BUG-152 п.4) — UZ-пользователь видел RU-кнопки;
  * RU-хардкод фолбэка адреса здания → ключ not_specified (BUG-152 п.3);
  * этаж/подъезд 0 легитимны (BUG-152 п.5, falsy-класс BUG-149);
  * days_ago в списке модерации считался вычитанием даты из САМОЙ СЕБЯ —
    метка «N дней» не показывалась никогда (BUG-152 п.5); теперь возраст
    заявки в бизнес-зоне (канон ARCH-116);
  * BUG-177: перепроверка роли ревьюера в ТОЧКЕ ЗАПИСИ решения модерации
    (канон BUG-172) — approve/reject с не-админом падают до записи; API
    отдаёт 403 через AddressPermissionError.
"""
from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from uk_management_bot.utils.helpers import get_text


# ══════════════════════════════════════════════════════════════════════════
# days_ago в клавиатуре модерации (BUG-152 п.5)
# ══════════════════════════════════════════════════════════════════════════


def _moderation_row(requested_at):
    return SimpleNamespace(
        id=1,
        user=SimpleNamespace(first_name="Житель", last_name=None,
                             telegram_id=100),
        apartment=SimpleNamespace(
            apartment_number="5",
            building=SimpleNamespace(address="Тестовая 1"),
        ),
        requested_at=requested_at,
    )


class TestModerationDaysAgo:
    def test_three_day_old_request_shows_age(self):
        from uk_management_bot.keyboards.address_management import (
            get_moderation_requests_keyboard,
        )

        req = _moderation_row(datetime.now(timezone.utc) - timedelta(days=3))
        markup = get_moderation_requests_keyboard([req], page=0, language="ru")
        button_text = markup.inline_keyboard[0][0].text
        days_short = get_text("address.keyboards.days_short", language="ru")
        assert f"3{days_short}" in button_text, button_text

    def test_fresh_request_has_no_age_label(self):
        from uk_management_bot.keyboards.address_management import (
            get_moderation_requests_keyboard,
        )

        req = _moderation_row(datetime.now(timezone.utc))
        markup = get_moderation_requests_keyboard([req], page=0, language="ru")
        button_text = markup.inline_keyboard[0][0].text
        days_short = get_text("address.keyboards.days_short", language="ru")
        assert days_short not in button_text

    def test_null_requested_at_does_not_crash(self):
        from uk_management_bot.keyboards.address_management import (
            get_moderation_requests_keyboard,
        )

        markup = get_moderation_requests_keyboard(
            [_moderation_row(None)], page=0, language="ru")
        assert markup.inline_keyboard


# ══════════════════════════════════════════════════════════════════════════
# Пробросы language и фолбэки (BUG-152 пп.3–4) — пины по исходнику
# ══════════════════════════════════════════════════════════════════════════


class TestLanguageReachesKeyboards:
    def test_no_ru_hardcoded_fallback_left(self):
        from uk_management_bot.handlers import user_apartment_selection as mod

        src = inspect.getsource(mod)
        assert "'Не указан'" not in src
        assert "user_apt_selection.handlers.not_specified" in src

    def test_document_keyboard_sites_carry_language(self):
        from uk_management_bot.handlers import user_apartment_selection as mod

        src = inspect.getsource(mod)
        assert "get_document_type_keyboard()" not in src
        assert src.count("get_document_type_keyboard(language=lang)") == 3

    def test_selection_keyboards_carry_language(self):
        from uk_management_bot.handlers import user_apartment_selection as mod

        src = inspect.getsource(mod)
        # три шага выбора + подтверждение
        assert src.count('"user_apartment_yard",\n                language=lang') == 1
        assert src.count('"user_apartment_building",\n                language=lang') == 1
        assert src.count('"user_apartment_final",\n                language=lang') == 1
        assert 'cancel_callback="user_apartment_cancel",\n                language=lang' in src

    def test_moderation_keyboards_carry_language(self):
        from uk_management_bot.handlers import address_moderation as mod

        src = inspect.getsource(mod)
        assert src.count("get_moderation_requests_keyboard(") == \
            src.count("language=lang)") or \
            "get_moderation_requests_keyboard([], page=0, language=lang)" in src

    def test_floor_and_entrance_zero_are_shown(self):
        from uk_management_bot.handlers import user_apartment_selection as mod

        src = inspect.getsource(mod)
        assert "if apartment.floor is not None:" in src
        assert "if apartment.entrance is not None:" in src
        assert "if apartment.floor:" not in src


# ══════════════════════════════════════════════════════════════════════════
# BUG-177 — роль ревьюера в точке записи решения модерации
# ══════════════════════════════════════════════════════════════════════════


async def _seed_pending(db):
    from uk_management_bot.database.models import (
        Apartment, Building, UserApartment, Yard,
    )
    from uk_management_bot.database.models.user import User

    manager = User(telegram_id=111, roles='["manager"]', status="approved")
    resident = User(telegram_id=222, roles='["applicant"]', status="approved")
    db.add_all([manager, resident])
    await db.flush()
    yard = Yard(name="Двор-177")
    db.add(yard)
    await db.flush()
    building = Building(address="Тестовая 177", yard_id=yard.id)
    db.add(building)
    await db.flush()
    apartment = Apartment(building_id=building.id, apartment_number="7")
    db.add(apartment)
    await db.flush()
    ua = UserApartment(user_id=resident.id, apartment_id=apartment.id,
                       status="pending")
    db.add(ua)
    await db.flush()
    return manager, resident, ua


class TestModerationWriteGate:
    @pytest.mark.asyncio
    async def test_non_admin_reviewer_is_refused_before_write(self, address_async_db):
        from uk_management_bot.database.models import UserApartment
        from uk_management_bot.services.addresses import core
        from uk_management_bot.services.addresses.exceptions import (
            AddressPermissionError,
        )

        _, resident, ua = await _seed_pending(address_async_db)
        with pytest.raises(AddressPermissionError):
            await core.approve_apartment_request(
                address_async_db, user_apartment_id=ua.id,
                reviewer_id=resident.id)
        fresh = await address_async_db.get(UserApartment, ua.id)
        assert fresh.status == "pending", "отказ обязан случиться ДО записи"

    @pytest.mark.asyncio
    async def test_reject_gate_mirrors_approve(self, address_async_db):
        from uk_management_bot.services.addresses import core
        from uk_management_bot.services.addresses.exceptions import (
            AddressPermissionError,
        )

        _, resident, ua = await _seed_pending(address_async_db)
        with pytest.raises(AddressPermissionError):
            await core.reject_apartment_request(
                address_async_db, user_apartment_id=ua.id,
                reviewer_id=resident.id, comment="нет")

    @pytest.mark.asyncio
    async def test_manager_reviewer_still_passes(self, address_async_db, monkeypatch):
        from uk_management_bot.config.settings import settings
        from uk_management_bot.services.addresses import core

        async def _noop(event, data):
            return None

        monkeypatch.setattr(core, "publish_realtime_after_commit", _noop)
        monkeypatch.setattr(settings, "INFRASAFE_WEBHOOK_ENABLED", True,
                            raising=False)

        manager, _, ua = await _seed_pending(address_async_db)
        result = await core.approve_apartment_request(
            address_async_db, user_apartment_id=ua.id, reviewer_id=manager.id)
        assert result.status == "approved"

    def test_api_maps_permission_error_to_403(self):
        from uk_management_bot.api.addresses import exception_handlers as eh
        from uk_management_bot.services.addresses.exceptions import (
            AddressPermissionError,
        )

        src = inspect.getsource(eh.register_address_exception_handlers)
        assert "AddressPermissionError" in src
        assert issubclass(AddressPermissionError, Exception)
