"""BUG-149 (пп.3–4) + BUG-151 (пп.2,3,5,6,7,8) — волна A2, батч 1.

Языковые пункты обоих (BUG-149 пп.1–2, BUG-151 п.4) закрыты волной BUG-165 и
держатся её гейтом. Здесь остальное:

  * GPS `0.0` falsy (BUG-149 п.3, BUG-151 п.7) — сравнение по `is not None`;
  * сырые ключи специализаций в списке смен (BUG-149 п.4) — общий `_loc_spec`;
  * NULL-guard `requested_at.strftime` (BUG-151 п.2);
  * `admin_comment` — рендер на языке ВЛАДЕЛЬЦА квартиры (BUG-151 п.3):
    комментарий хранится строкой и читает его житель (reason в списке);
  * список зданий без фильтра `is_active` (BUG-151 п.5, паттерн дворов);
  * хендлер пагинации `addr_buildings_by_yard_page:` (BUG-151 п.6 — кнопки
    страниц по двору были мертвы: клавиатура генерила callback без хендлера);
  * свежая клавиатура после сохранения телефона/имени/фамилии (BUG-151 п.8,
    рецепт BUG-BOT-020: view возвращается из юнита записи).
"""
from __future__ import annotations

import inspect
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from uk_management_bot.utils.helpers import get_text


@pytest.fixture()
def db():
    from uk_management_bot.database.models.building import Building  # noqa: F401
    from uk_management_bot.database.models.user import User  # noqa: F401
    from uk_management_bot.database.models.yard import Yard  # noqa: F401
    from uk_management_bot.database.session import Base

    engine = create_engine(
        "sqlite://", poolclass=StaticPool,
        connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = Factory()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)


def _callback(data: str) -> SimpleNamespace:
    return SimpleNamespace(
        data=data,
        from_user=SimpleNamespace(id=100),
        message=SimpleNamespace(edit_text=AsyncMock(), answer=AsyncMock()),
        answer=AsyncMock(),
    )


# ══════════════════════════════════════════════════════════════════════════
# GPS 0.0 (BUG-149 п.3, BUG-151 п.7)
# ══════════════════════════════════════════════════════════════════════════


class TestGpsZeroIsLegitimate:
    @pytest.mark.asyncio
    async def test_yard_details_render_zero_coordinates(self, db):
        from uk_management_bot.database.models.yard import Yard
        from uk_management_bot.handlers.address_yards import show_yard_details

        db.add(Yard(id=1, name="Нулевой", gps_latitude=0.0, gps_longitude=0.0))
        db.commit()

        cb = _callback("addr_yard_view:1")
        await show_yard_details(cb, language="ru", _db=db)

        cb.message.edit_text.assert_awaited()
        text = cb.message.edit_text.await_args.args[0]
        assert "0.0" in text
        assert get_text("address_yards.handlers.gps_not_set", language="ru") not in text

    def test_no_falsy_gps_comparison_left(self):
        """Пин всех четырёх сайтов разом: паттерн `gps_latitude and` ушёл."""
        from uk_management_bot.handlers import address_buildings, address_yards

        for mod in (address_yards, address_buildings):
            src = inspect.getsource(mod)
            assert "gps_latitude and " not in src, mod.__name__
            assert "gps_latitude is not None" in src, mod.__name__


# ══════════════════════════════════════════════════════════════════════════
# Специализации в списке смен (BUG-149 п.4)
# ══════════════════════════════════════════════════════════════════════════


class TestShiftSpecLocalization:
    def test_loc_spec_localizes_known_key(self):
        from uk_management_bot.handlers.shifts import _loc_spec

        assert _loc_spec("plumber", "ru") == get_text(
            "specializations.plumber", language="ru")
        assert _loc_spec("plumber", "ru") != "plumber"

    def test_loc_spec_falls_back_to_raw_for_unknown(self):
        from uk_management_bot.handlers.shifts import _loc_spec

        assert _loc_spec("no_such_spec", "ru") == "no_such_spec"

    def test_both_renderers_share_the_helper(self):
        """Список (end_shift_confirm) и детали (show_shift_end_details) обязаны
        локализовать одним хелпером — рассинхрон и был дефектом."""
        from uk_management_bot.handlers import shifts

        assert "_loc_spec(s, lang)" in inspect.getsource(shifts.end_shift_confirm)
        assert "_loc_spec(s, lang)" in inspect.getsource(shifts.show_shift_end_details)


# ══════════════════════════════════════════════════════════════════════════
# admin_comment на языке владельца (BUG-151 п.3)
# ══════════════════════════════════════════════════════════════════════════


def _seed_apartment_request(db, *, owner_lang: str):
    from uk_management_bot.database.models import Apartment, UserApartment
    from uk_management_bot.database.models.building import Building
    from uk_management_bot.database.models.user import User
    from uk_management_bot.database.models.yard import Yard

    db.add(User(id=1, telegram_id=100, first_name="Админ",
                roles='["manager"]', status="approved", language="ru"))
    db.add(User(id=2, telegram_id=200, first_name="Житель",
                roles='["applicant"]', status="approved", language=owner_lang))
    db.add(Yard(id=1, name="Двор"))
    db.add(Building(id=1, address="Тестовая 1", yard_id=1))
    db.add(Apartment(id=1, building_id=1, apartment_number="5"))
    db.add(UserApartment(id=1, user_id=2, apartment_id=1, status="pending"))
    db.commit()


class TestAdminCommentOwnerLanguage:
    def test_approve_comment_in_owner_language(self, db):
        from uk_management_bot.database.models import UserApartment
        from uk_management_bot.handlers.user_apartments import (
            _admin_approve_apartment,
        )

        _seed_apartment_request(db, owner_lang="uz")
        assert _admin_approve_apartment(db, 1, 100) == "ok"
        ua = db.get(UserApartment, 1)
        expected = get_text(
            "user_apartments.admin_comment_approved", language="uz"
        ).format(name="Админ")
        assert ua.admin_comment == expected

    def test_reject_comment_in_owner_language(self, db):
        from uk_management_bot.database.models import UserApartment
        from uk_management_bot.handlers.user_apartments import (
            _admin_reject_apartment,
        )

        _seed_apartment_request(db, owner_lang="uz")
        assert _admin_reject_apartment(db, 1, 100) == "ok"
        ua = db.get(UserApartment, 1)
        expected = get_text(
            "user_apartments.admin_comment_rejected", language="uz"
        ).format(name="Админ")
        assert ua.admin_comment == expected

    def test_locale_keys_exist_in_both_languages(self):
        for key in ("user_apartments.admin_comment_approved",
                    "user_apartments.admin_comment_rejected"):
            for lang in ("ru", "uz"):
                text = get_text(key, language=lang)
                assert text != key, f"{key} отсутствует в {lang}"
                assert "{name}" in text


# ══════════════════════════════════════════════════════════════════════════
# Список зданий без фильтра is_active (BUG-151 п.5)
# ══════════════════════════════════════════════════════════════════════════


class TestBuildingsOverviewIncludesInactive:
    def test_inactive_building_listed(self, db):
        from uk_management_bot.database.models.building import Building
        from uk_management_bot.database.models.yard import Yard
        from uk_management_bot.handlers.address_buildings import (
            _load_buildings_overview,
        )

        db.add(Yard(id=1, name="Двор"))
        db.add(Building(id=1, address="Активное 1", yard_id=1, is_active=True))
        db.add(Building(id=2, address="Неактивное 2", yard_id=1, is_active=False))
        db.commit()

        rows = _load_buildings_overview(db)
        assert len(rows) == 2
        assert {r.is_active for r in rows} == {True, False}


# ══════════════════════════════════════════════════════════════════════════
# Пагинация зданий по двору (BUG-151 п.6)
# ══════════════════════════════════════════════════════════════════════════


class TestBuildingsByYardPagination:
    @pytest.mark.asyncio
    async def test_page_handler_renders_requested_page(self, db):
        from uk_management_bot.database.models.building import Building
        from uk_management_bot.database.models.yard import Yard
        from uk_management_bot.handlers.address_buildings import (
            show_buildings_by_yard_page,
        )

        db.add(Yard(id=1, name="Большой двор"))
        for i in range(1, 8):
            db.add(Building(id=i, address=f"Дом {i}", yard_id=1))
        db.commit()

        cb = _callback("addr_buildings_by_yard_page:1:1")
        await show_buildings_by_yard_page(cb, language="ru", _db=db)

        cb.message.edit_text.assert_awaited()
        text = cb.message.edit_text.await_args.args[0]
        assert "Большой двор" in text
        markup = cb.message.edit_text.await_args.kwargs["reply_markup"]
        assert markup is not None

    @pytest.mark.asyncio
    async def test_unknown_yard_is_honest_refusal(self, db):
        from uk_management_bot.handlers.address_buildings import (
            show_buildings_by_yard_page,
        )

        cb = _callback("addr_buildings_by_yard_page:999:0")
        await show_buildings_by_yard_page(cb, language="ru", _db=db)
        cb.answer.assert_awaited_with(
            get_text("address_buildings.handlers.yard_not_found", language="ru"),
            show_alert=True)


# ══════════════════════════════════════════════════════════════════════════
# Свежая клавиатура профиля после сохранения (BUG-151 п.8)
# ══════════════════════════════════════════════════════════════════════════


class TestProfileKeyboardFreshAfterSave:
    def _seed_user(self, db):
        from uk_management_bot.database.models.user import User

        db.add(User(id=1, telegram_id=100, roles='["applicant"]',
                    status="approved", language="ru"))
        db.commit()

    def test_phone_unit_returns_fresh_view(self, db):
        from uk_management_bot.handlers.profile_editing import _update_user_phone

        self._seed_user(db)
        view = _update_user_phone(db, 100, "+998901234567")
        assert view is not None
        assert view.phone == "+998901234567"

    def test_unknown_user_returns_none(self, db):
        from uk_management_bot.handlers.profile_editing import _update_user_phone

        assert _update_user_phone(db, 999, "+998901234567") is None

    @pytest.mark.parametrize("unit_name,field,value", [
        ("_update_user_first_name", "first_name", "Алишер"),
        ("_update_user_last_name", "last_name", "Навоий"),
    ])
    def test_name_units_return_fresh_view(self, db, unit_name, field, value):
        from uk_management_bot.handlers import profile_editing

        self._seed_user(db)
        view = getattr(profile_editing, unit_name)(db, 100, value)
        assert view is not None
        assert getattr(view, field) == value

    def test_handlers_pass_view_to_keyboard(self):
        """Все три хендлера сохранения передают свежий view в клавиатуру —
        рендер без user и был дефектом («не указано» после сохранения)."""
        from uk_management_bot.handlers import profile_editing

        for name in ("handle_phone_input", "handle_first_name_input",
                     "handle_last_name_input"):
            src = inspect.getsource(getattr(profile_editing, name))
            assert "get_profile_edit_keyboard(lang, updated)" in src, name
