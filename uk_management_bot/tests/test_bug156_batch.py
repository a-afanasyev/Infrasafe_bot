"""BUG-156 — волна A2, батч 3 (address_apartments + roles_specs).

  * п.1 — language в клавиатуры списка/карточки квартир (пины);
  * п.2 — мёртвые кнопки страниц поиска не рендерятся (show_pagination=False);
  * п.3 — подъезд/этаж/комнаты/площадь 0 показываются (is not None);
  * п.4 — сырые коды ошибок сервиса → localize_address_error;
  * п.5 — выбор здания при создании: limit(50) снят, список листается
    пагинацией (`apartment_create_bpage:<n>` под StateFilter своего шага);
  * п.6 — нетекстовое сообщение в FSM-шагах цепочки создания/автозаполнения
    и в шагах комментария ролей/специализаций — честный отказ, а не
    AttributeError/null в аудите;
  * п.7 — набор ролей применяется ОДНОЙ транзакцией (commit=False у сервиса,
    отказ на середине откатывает всё);
  * п.8 — права перепроверяются на каждом шаге цепочки ролей/специализаций.
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
    from uk_management_bot.database.models import (  # noqa: F401
        Apartment, Building, Yard,
    )
    from uk_management_bot.database.models.user import User  # noqa: F401
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


def _message(text):
    return SimpleNamespace(
        text=text,
        from_user=SimpleNamespace(id=100),
        answer=AsyncMock(),
    )


def _state():
    return SimpleNamespace(
        get_data=AsyncMock(return_value={}),
        update_data=AsyncMock(),
        set_state=AsyncMock(),
        clear=AsyncMock(),
    )


# ══════════════════════════════════════════════════════════════════════════
# п.6 — нетекстовые сообщения в FSM-шагах
# ══════════════════════════════════════════════════════════════════════════


class TestNonTextGuards:
    @pytest.mark.asyncio
    async def test_apartment_number_step_refuses_non_text(self):
        from uk_management_bot.handlers.address_apartments.creation import (
            process_apartment_number,
        )

        msg = _message(None)  # фото/стикер: message.text is None
        state = _state()
        await process_apartment_number(msg, state, language="ru")
        msg.answer.assert_awaited_with(
            get_text("errors.invalid_input", language="ru"))
        state.update_data.assert_not_awaited()

    def test_every_text_step_in_creation_chain_is_guarded(self):
        """Guard стоит в КАЖДОМ шаге цепочки (класс общий, BUG-145 п.4)."""
        from uk_management_bot.handlers.address_apartments import (
            autofill, creation,
        )

        assert inspect.getsource(creation).count("if not message.text:") == 5
        assert inspect.getsource(autofill).count("if not message.text:") == 1

    @pytest.mark.asyncio
    async def test_role_comment_step_refuses_non_text(self):
        from uk_management_bot.handlers.user_management.roles_specs import (
            process_role_change_comment,
        )

        msg = _message(None)
        state = _state()
        await process_role_change_comment(
            msg, state, language="ru", roles=["manager"],
            user=SimpleNamespace(id=1))
        msg.answer.assert_awaited_with(
            get_text("errors.invalid_input", language="ru"))


# ══════════════════════════════════════════════════════════════════════════
# п.8 — права на каждом шаге цепочки ролей/специализаций
# ══════════════════════════════════════════════════════════════════════════


class TestChainRightsRechecked:
    @pytest.mark.asyncio
    async def test_applicant_cannot_reach_role_toggle(self):
        from uk_management_bot.handlers.user_management.roles_specs import (
            add_role_to_user,
        )

        cb = SimpleNamespace(
            data="role_add_manager", answer=AsyncMock(),
            from_user=SimpleNamespace(id=100),
            message=SimpleNamespace(edit_text=AsyncMock()),
        )
        state = _state()
        await add_role_to_user(cb, state, language="ru",
                               roles=["applicant"], user=None)
        cb.answer.assert_awaited_with(
            get_text("errors.permission_denied", language="ru"),
            show_alert=True)
        state.get_data.assert_not_awaited()

    def test_all_chain_handlers_carry_the_guard(self):
        from uk_management_bot.handlers.user_management import roles_specs

        for fn in ("add_role_to_user", "remove_role_from_user",
                   "save_user_roles", "process_role_change_comment",
                   "toggle_specialization", "save_user_specializations",
                   "process_specialization_change_comment"):
            body = inspect.getsource(getattr(roles_specs, fn))
            assert "has_admin_access(roles=roles, user=user)" in body, fn


# ══════════════════════════════════════════════════════════════════════════
# п.7 — транзакционное применение набора ролей
# ══════════════════════════════════════════════════════════════════════════


class TestRolesAppliedAtomically:
    def _seed(self, db):
        from uk_management_bot.database.models.user import User

        db.add(User(id=1, telegram_id=100, roles='["manager"]',
                    status="approved"))
        db.add(User(id=2, telegram_id=200, roles='["applicant"]',
                    status="approved"))
        db.commit()

    def test_failure_mid_batch_rolls_back_everything(self, db):
        from uk_management_bot.database.models.user import User
        from uk_management_bot.handlers.user_management.roles_specs import (
            _apply_role_changes,
        )

        self._seed(db)
        # executor применился бы, «no_such_role» отвергается валидацией сервиса
        success, *_ = _apply_role_changes(
            db, 2, ["executor", "no_such_role"], [], 1, "тест", "ru")
        assert success is False
        db.expire_all()
        user = db.get(User, 2)
        assert "executor" not in (user.roles or ""), \
            "частично применённые роли обязаны откатиться"

    def test_successful_batch_commits_all(self, db):
        from uk_management_bot.database.models.user import User
        from uk_management_bot.handlers.user_management.roles_specs import (
            _apply_role_changes,
        )

        self._seed(db)
        success, user_name, _info, _kb = _apply_role_changes(
            db, 2, ["executor"], [], 1, "тест", "ru")
        assert success is True
        db.expire_all()
        assert "executor" in db.get(User, 2).roles


# ══════════════════════════════════════════════════════════════════════════
# п.5 — пагинация выбора здания при создании
# ══════════════════════════════════════════════════════════════════════════


def _buildings(n):
    return [SimpleNamespace(id=i, address=f"Дом {i:03d}") for i in range(1, n + 1)]


class TestCreateBuildingPagination:
    def test_keyboard_paginated_mode_slices_and_navigates(self):
        from uk_management_bot.keyboards.address_management import (
            get_user_apartment_selection_keyboard,
        )

        markup = get_user_apartment_selection_keyboard(
            _buildings(25), "building", "apartment_create_building",
            language="ru", page=0, page_prefix="apartment_create_bpage")
        callbacks = [b.callback_data for row in markup.inline_keyboard for b in row]
        assert "apartment_create_building:1" in callbacks
        assert "apartment_create_building:11" not in callbacks, "страница = 10"
        assert "apartment_create_bpage:1" in callbacks, "нет кнопки «вперёд»"

    def test_flat_mode_unchanged_for_resident_flow(self):
        """Без page/page_prefix — прежний плоский список (жительские флоу)."""
        from uk_management_bot.keyboards.address_management import (
            get_user_apartment_selection_keyboard,
        )

        markup = get_user_apartment_selection_keyboard(
            _buildings(25), "building", "user_apartment_building",
            language="ru")
        callbacks = [b.callback_data for row in markup.inline_keyboard for b in row]
        assert "user_apartment_building:25" in callbacks
        assert not any("bpage" in c for c in callbacks)

    def test_no_limit_left_in_loader(self):
        from uk_management_bot.handlers.address_apartments import creation

        assert ".limit(50)" not in inspect.getsource(creation._load_active_buildings)

    @pytest.mark.asyncio
    async def test_page_handler_renders_requested_page(self, db):
        from uk_management_bot.database.models import Building, Yard
        from uk_management_bot.handlers.address_apartments.creation import (
            show_create_buildings_page,
        )

        db.add(Yard(id=1, name="Двор"))
        for i in range(1, 13):
            db.add(Building(id=i, address=f"Дом {i:03d}", yard_id=1))
        db.commit()

        cb = SimpleNamespace(
            data="apartment_create_bpage:1", answer=AsyncMock(),
            from_user=SimpleNamespace(id=100),
            message=SimpleNamespace(edit_text=AsyncMock()),
        )
        await show_create_buildings_page(cb, _state(), language="ru", _db=db)
        cb.message.edit_text.assert_awaited()
        markup = cb.message.edit_text.await_args.kwargs["reply_markup"]
        callbacks = [b.callback_data for row in markup.inline_keyboard for b in row]
        assert "apartment_create_building:11" in callbacks
        assert "apartment_create_bpage:0" in callbacks, "нет кнопки «назад»"

    @pytest.mark.asyncio
    async def test_malformed_page_is_silently_answered(self, db):
        from uk_management_bot.handlers.address_apartments.creation import (
            show_create_buildings_page,
        )

        cb = SimpleNamespace(
            data="apartment_create_bpage:²", answer=AsyncMock(),
            from_user=SimpleNamespace(id=100),
            message=SimpleNamespace(edit_text=AsyncMock()),
        )
        await show_create_buildings_page(cb, _state(), language="ru", _db=db)
        cb.answer.assert_awaited()
        cb.message.edit_text.assert_not_awaited()


# ══════════════════════════════════════════════════════════════════════════
# пп.1–4 — пины по исходнику (рендер-дефекты без поведения)
# ══════════════════════════════════════════════════════════════════════════


class TestRenderPins:
    def test_search_results_render_without_dead_page_buttons(self, db):
        from uk_management_bot.database.models import Apartment, Building, Yard
        from uk_management_bot.handlers.address_apartments.viewing import (
            _search_apartments_markup,
        )

        db.add(Yard(id=1, name="Двор"))
        db.add(Building(id=1, address="Поисковая 1", yard_id=1))
        for i in range(1, 16):
            db.add(Apartment(id=i, building_id=1, apartment_number=str(i)))
        db.commit()

        total, markup = _search_apartments_markup(db, "Поисковая", "ru")
        assert total == 15
        callbacks = [b.callback_data for row in markup.inline_keyboard for b in row]
        assert not any(c.startswith("addr_apartments_page") for c in callbacks), \
            "мёртвые кнопки страниц поиска не должны рендериться"

    def test_details_falsy_zero_pinned(self):
        from uk_management_bot.handlers.address_apartments import details

        src = inspect.getsource(details)
        for field in ("entrance", "floor", "rooms_count", "area"):
            assert f"apartment.{field} is not None" in src, field

    def test_keyboards_carry_language_pinned(self):
        from uk_management_bot.handlers.address_apartments import viewing

        assert "language=lang" in inspect.getsource(viewing._load_building_apartments)
        assert "show_pagination=False" in inspect.getsource(
            viewing._search_apartments_markup)

    def test_raw_error_codes_localized(self):
        from uk_management_bot.handlers.address_apartments import creation, editing

        assert inspect.getsource(editing).count("localize_address_error(error, lang)") == 3
        assert "localize_address_error(error, lang)" in inspect.getsource(creation)
