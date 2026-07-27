"""DEAD-134: вход в комментарии и отчёт на ЖИВЫХ карточках заявки.

Хендлеры `view_comments_` / `add_comment_` / `view_report_` были написаны
целиком и зарегистрированы в диспетчере, но попасть в них было нельзя: кнопки
объявлялись только в шести билдерах клавиатур с нулём вызовов. Это в точности
тот же класс, что регресс «📦 Материалы» (см. соседний
`test_view_request_materials_button.py`): кнопка в мёртвой клавиатуре, а живая
карточка собирается инлайн в хендлере.

Поэтому тесты бьют по живому пути — реальная sqlite-сессия и вызов самих
хендлеров карточек, — а не по билдеру строк. Билдер проверяется отдельно, но
его зелень ничего не доказывала бы: ровно так баг и появился.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.user import User
from uk_management_bot.database.session import Base
from uk_management_bot.handlers.admin import views as admin_views
from uk_management_bot.handlers.requests import listing
from uk_management_bot.keyboards.requests import get_discussion_rows

MANAGER_TG = 700100
APPLICANT_TG = 700200
NUMBER = "260705-960"


def _callbacks(markup) -> list[str]:
    return [b.callback_data for row in markup.inline_keyboard for b in row]


@pytest.fixture
def db(monkeypatch):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()

    @contextmanager
    def fake_scope(_):
        yield session

    monkeypatch.setattr(listing, "_db_scope", fake_scope)
    monkeypatch.setattr(listing, "get_user_language", lambda *a, **k: "ru")
    yield session
    session.close()


def _seed(db, *, status="В работе", report=None):
    manager = User(id=1, telegram_id=MANAGER_TG, first_name="Mgr",
                   roles='["manager"]', active_role="manager", status="approved")
    applicant = User(id=2, telegram_id=APPLICANT_TG, first_name="App",
                     roles='["applicant"]', active_role="applicant", status="approved")
    db.add_all([manager, applicant])
    db.flush()
    req = Request(request_number=NUMBER, user_id=2, category="electrics",
                  status=status, description="тест", urgency="medium",
                  address="x", created_at=datetime.now(timezone.utc),
                  completion_report=report,
                  is_returned=False, manager_confirmed=False)
    db.add(req)
    db.commit()
    return manager, applicant, req


def _callback(data: str, telegram_id: int):
    cb = MagicMock()
    cb.data = data
    cb.from_user.id = telegram_id
    cb.answer = AsyncMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.message.answer = AsyncMock()
    return cb


def _state():
    st = AsyncMock()
    st.get_data = AsyncMock(return_value={"my_requests_page": 1})
    return st


class TestManagerCardHasTheEntrance:
    """Карточка `mview_` — та самая, что открывается в живом боте."""

    @pytest.mark.asyncio
    async def test_active_request_card_offers_comments(self, db):
        manager, _, _ = _seed(db, status="В работе")
        cb = _callback(f"mview_{NUMBER}", MANAGER_TG)

        await admin_views.handle_manager_view_request(
            cb, db=db, roles=["manager"], active_role="manager",
            user=manager, language="ru",
        )

        cbs = _callbacks(cb.message.edit_text.await_args.kwargs["reply_markup"])
        assert f"view_comments_{NUMBER}" in cbs, f"нет входа в комментарии: {cbs}"
        assert f"add_comment_{NUMBER}" in cbs, f"нет добавления комментария: {cbs}"
        # прежние действия менеджера не потеряны
        assert f"mgr_complete_{NUMBER}" in cbs and f"mreq_back_{NUMBER}" in cbs

    @pytest.mark.asyncio
    async def test_report_button_appears_only_with_a_report(self, db):
        """Кнопка «на всякий случай» обещала бы то, чего нет.

        Хендлер на заявке без отчёта отвечает алертом «отчёта пока нет» —
        показывать её в этом случае значит отправлять человека в тупик.
        """
        manager, _, _ = _seed(db, status="В работе", report=None)
        cb = _callback(f"mview_{NUMBER}", MANAGER_TG)
        await admin_views.handle_manager_view_request(
            cb, db=db, roles=["manager"], active_role="manager",
            user=manager, language="ru",
        )
        assert not any(
            c.startswith("view_report_")
            for c in _callbacks(cb.message.edit_text.await_args.kwargs["reply_markup"])
        )

    @pytest.mark.asyncio
    async def test_report_button_present_when_report_written(self, db):
        manager, _, _ = _seed(db, status="Выполнена", report="всё сделано")
        cb = _callback(f"mview_{NUMBER}", MANAGER_TG)
        await admin_views.handle_manager_view_request(
            cb, db=db, roles=["manager"], active_role="manager",
            user=manager, language="ru",
        )
        cbs = _callbacks(cb.message.edit_text.await_args.kwargs["reply_markup"])
        assert f"view_report_{NUMBER}" in cbs, f"нет входа в отчёт: {cbs}"


class TestApplicantCardHasTheEntrance:
    """Карточка `view_` из «Мои заявки» — второй живой вход."""

    @pytest.mark.asyncio
    async def test_applicant_card_offers_comments(self, db):
        _seed(db, status="В работе")
        cb = _callback(f"view_request_{NUMBER}", APPLICANT_TG)

        await listing.handle_view_request(cb, _state())

        cbs = _callbacks(cb.message.edit_text.await_args.kwargs["reply_markup"])
        assert f"view_comments_{NUMBER}" in cbs, f"нет входа в комментарии: {cbs}"
        assert "back_list_1" in cbs, "потеряна кнопка возврата"


class TestDiscussionRowsBuilder:
    def test_report_row_is_conditional(self):
        without = get_discussion_rows(NUMBER, has_report=False)
        with_report = get_discussion_rows(NUMBER, has_report=True)

        def flat(rows):
            return [b.callback_data for r in rows for b in r]

        assert f"view_report_{NUMBER}" not in flat(without)
        assert f"view_report_{NUMBER}" in flat(with_report)

    def test_callbacks_match_what_the_handlers_listen_for(self):
        """Префиксы сверяются с фильтрами хендлеров, а не с памятью автора.

        Именно рассинхрон «кнопка шлёт одно, хендлер ждёт другое» дал бы
        зелёный билдер и мёртвую кнопку.
        """
        import inspect

        from uk_management_bot.handlers import request_comments, request_reports

        sources = inspect.getsource(request_comments) + inspect.getsource(request_reports)
        for prefix in ("view_comments_", "add_comment_", "view_report_"):
            assert f'F.data.startswith("{prefix}")' in sources, (
                f"хендлер на префикс {prefix} не найден — кнопка вела бы в никуда"
            )


def test_live_cards_reference_the_shared_builder():
    """Гейт против возврата в исходное состояние.

    Пункт DEAD-134 родился из того, что кнопки жили в билдерах, которые никто
    не вызывает. Если из живых карточек уйдёт вызов общего билдера, вход снова
    исчезнет — а функциональные тесты выше это поймают только пока сами живы.
    """
    import inspect

    for module in (admin_views, listing):
        # Проверяется ВЫЗОВ (со скобкой), а не упоминание имени: при откате,
        # удалившем только вызовы, импорт `get_discussion_rows,` оставался — и
        # проверка по имени переживала откат, то есть не проверяла ничего.
        assert "get_discussion_rows(" in inspect.getsource(module), (
            f"{module.__name__} больше не подключает строки обсуждения — "
            "вход в комментарии/отчёт снова стал недостижим"
        )
