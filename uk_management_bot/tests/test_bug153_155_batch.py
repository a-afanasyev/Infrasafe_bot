"""BUG-153 (пп.1–4,6) + BUG-155 (пп.4,7) — волна A2, хвост.

BUG-153 (unaccepted_requests / request_reports):
  * п.1 — уведомления рендерятся на языке ПОЛУЧАТЕЛЯ (заявителя/исполнителя),
    а не менеджера, нажавшего кнопку;
  * п.2 — RU-хардкоды через локаль: шапка комментария менеджера, суффиксы
    «д/ч/м», «неизв.», текст комментария о доработке;
  * п.3 — falsy-0 executor_id → is not None;
  * п.4 — id-микс: единый резолв telegram_id → users.id (кнопки заявителя
    «принять/доработка» отвечали «нет доступа» ВСЕГДА — путь оживлён, мутации
    дальше идут каноном, который авторизует владельца сам);
  * п.6 — completed_at через fmt_datetime (канон бизнес-зоны ARCH-116).

BUG-155 (user_management/actions):
  * п.4 — state.clear() ставился ПОСЛЕ update_data и стирал записанное;
  * п.7 — NULL-strftime у документов и falsy file_size (0 байт — легитимный
    размер).
"""
from __future__ import annotations

import inspect

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from uk_management_bot.utils.helpers import get_text


@pytest.fixture()
def db():
    from uk_management_bot.database.models.request import Request  # noqa: F401
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


# ══════════════════════════════════════════════════════════════════════════
# BUG-153 п.1/п.3 — адресаты и их язык
# ══════════════════════════════════════════════════════════════════════════


class TestNotifyTargetsCarryRecipientLanguage:
    def test_targets_resolve_languages(self, db):
        from uk_management_bot.database.models.user import User
        from uk_management_bot.handlers.unaccepted_requests import (
            _load_notify_targets,
        )

        db.add(User(id=1, telegram_id=100, language="uz",
                    roles='["applicant"]', status="approved"))
        db.add(User(id=2, telegram_id=200, language="ru",
                    roles='["executor"]', status="approved"))
        db.commit()

        targets = _load_notify_targets(db, 1, 2)
        assert targets.applicant_language == "uz"
        assert targets.executor_language == "ru"
        assert targets.applicant_telegram_id == 100
        assert targets.executor_telegram_id == 200

    def test_send_sites_use_recipient_language(self):
        from uk_management_bot.handlers import unaccepted_requests as mod

        src = inspect.getsource(mod)
        assert "language=targets.applicant_language" in src
        assert "language=targets.executor_language" in src
        assert "recipient_lang = applicant.language" in src

    def test_executor_id_zero_is_not_missing(self):
        from uk_management_bot.handlers import unaccepted_requests as mod

        src = inspect.getsource(mod._load_notify_targets)
        assert "if executor_id is not None:" in src


# ══════════════════════════════════════════════════════════════════════════
# BUG-153 п.2 — локали вместо RU-хардкодов
# ══════════════════════════════════════════════════════════════════════════


class TestHardcodesLocalized:
    @pytest.mark.parametrize("key", [
        "unaccepted.handlers.days_short",
        "unaccepted.handlers.hours_short",
        "unaccepted.handlers.minutes_short",
        "unaccepted.handlers.unknown_short",
        "unaccepted.handlers.manager_comment_block",
        "request_reports.handlers.revision_comment",
    ])
    def test_keys_exist_in_both_languages(self, key):
        for lang in ("ru", "uz"):
            assert get_text(key, language=lang) != key, f"{key} нет в {lang}"

    def test_no_raw_hardcodes_left(self):
        from uk_management_bot.handlers import request_reports, unaccepted_requests

        src = inspect.getsource(unaccepted_requests)
        assert 'time_str = "неизв."' not in src
        assert "ПРИНЯТО МЕНЕДЖЕРОМ" not in src
        assert "Запрошена доработка. Причина:" not in inspect.getsource(request_reports)


# ══════════════════════════════════════════════════════════════════════════
# BUG-153 п.4 — id-микс: кнопки заявителя оживают
# ══════════════════════════════════════════════════════════════════════════


class TestApplicantActionContextIdResolution:
    def _seed(self, db):
        from uk_management_bot.database.models.request import Request
        from uk_management_bot.database.models.user import User

        # telegram_id НАМЕРЕННО не совпадает с id: id-микс это и ловит
        db.add(User(id=5, telegram_id=555000, roles='["applicant"]',
                    status="approved", language="ru"))
        db.add(Request(request_number="260901-001", user_id=5,
                       category="electricity", description="d",
                       status="Исполнено", urgency="low"))
        db.commit()

    def test_owner_with_distinct_telegram_id_passes(self, db):
        from uk_management_bot.handlers.request_reports import (
            _load_applicant_action_context,
        )

        self._seed(db)
        verdict, brief = _load_applicant_action_context(db, "260901-001", 555000)
        assert verdict == "ok", \
            "владелец с telegram_id != users.id раньше получал «нет доступа»"

    def test_stranger_is_still_refused(self, db):
        from uk_management_bot.database.models.user import User
        from uk_management_bot.handlers.request_reports import (
            _load_applicant_action_context,
        )

        self._seed(db)
        db.add(User(id=6, telegram_id=666000, roles='["applicant"]',
                    status="approved"))
        db.commit()
        verdict, _ = _load_applicant_action_context(db, "260901-001", 666000)
        assert verdict == "not_owner"

    def test_non_applicant_refused(self, db):
        from uk_management_bot.database.models.user import User
        from uk_management_bot.handlers.request_reports import (
            _load_applicant_action_context,
        )

        self._seed(db)
        db.add(User(id=7, telegram_id=777000, roles='["executor"]',
                    status="approved"))
        db.commit()
        verdict, _ = _load_applicant_action_context(db, "260901-001", 777000)
        assert verdict == "no_role"


# ══════════════════════════════════════════════════════════════════════════
# BUG-153 п.6 + BUG-155 пп.4,7 — пины
# ══════════════════════════════════════════════════════════════════════════


class TestRemainingPins:
    def test_completed_at_goes_through_business_tz(self):
        from uk_management_bot.handlers import request_reports

        src = inspect.getsource(request_reports)
        assert "fmt_datetime(request.completed_at)" in src
        assert "request.completed_at.strftime" not in src

    def test_state_cleared_before_write_not_after(self):
        from uk_management_bot.handlers.user_management import actions

        src = inspect.getsource(actions.handle_request_documents)
        assert src.index("state.clear()") < src.index("state.update_data"), \
            "clear() после update_data стирал только что записанное"

    def test_document_rendering_guards(self):
        from uk_management_bot.handlers.user_management import actions

        src = inspect.getsource(actions)
        assert src.count("file_size is not None") == 2
        assert 'doc.created_at.strftime(\'%d.%m.%Y %H:%M\') if doc.created_at else "—"' in src
        assert 'if payload.created_at else "—"' in src
