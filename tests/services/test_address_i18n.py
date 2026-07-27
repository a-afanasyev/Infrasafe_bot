"""П8 / FS-11 + AUD5-CODE-12 — адрес и уведомление на языке ЧИТАТЕЛЯ.

`Apartment.full_address` — канонический RU-формат («…, кв. 5»): он уезжает в
БД и в поиск, поэтому языка знать не должен. Локализацией занимается показ, и
именно её не делали: `localize_address` жил только в рендере заявок, а
профиль, выбор квартиры и клавиатуры адресов показывали канон как есть.

Отдельная тонкость (AUD5-CODE-12): уведомление админам читает ДРУГОЙ человек.
Раньше адрес в нём приходил на языке заявителя, а сам текст — с хардкодом
`language='ru'`.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from uk_management_bot.database.models.apartment import Apartment
from uk_management_bot.database.models.building import Building
from uk_management_bot.database.models.yard import Yard
from uk_management_bot.database.models.user import User
from uk_management_bot.database.session import Base
from uk_management_bot.utils.address_helpers import apartment_address

RU_ADMIN, UZ_ADMIN = 5001, 5002
APPLICANT = 5003


@pytest.fixture()
def session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    s = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
    yield s
    s.close()
    engine.dispose()


@pytest.fixture()
def apartment(session) -> Apartment:
    yard = Yard(name="Yangi Olmazor")
    session.add(yard)
    session.flush()
    building = Building(yard_id=yard.id, address="Yangi Olmazor 14V")
    session.add(building)
    session.flush()
    apt = Apartment(building_id=building.id, apartment_number="1")
    session.add(apt)
    session.commit()
    return apt


class TestApartmentAddressCanon:
    def test_uzbek_reader_does_not_see_russian_apartment_prefix(self, apartment):
        """Суть FS-11: UZ-пользователь видел «кв.» в собственном профиле."""
        shown = apartment_address(apartment, "uz")

        assert "кв." not in shown, f"UZ-читатель видит русское сокращение: {shown!r}"
        assert "xon." in shown, shown

    def test_russian_reader_sees_the_canonical_form_unchanged(self, apartment):
        assert apartment_address(apartment, "ru") == apartment.full_address

    def test_canonical_property_stays_language_neutral(self, apartment):
        """Модель не должна начать локализовать сама — иначе канон поедет в БД."""
        assert "кв." in apartment.full_address
        assert "xon." not in apartment.full_address


PACKAGE_ROOT = Path(__file__).resolve().parents[2] / "uk_management_bot"
# Где `full_address` — это ДАННЫЕ, а не показ:
#   address_helpers — сам канон локализации;
#   profile_service — собирает канон, локализует его format_profile_text.
FULL_ADDRESS_ALLOWED = {
    "uk_management_bot/utils/address_helpers.py",
    "uk_management_bot/services/profile_service.py",
    "uk_management_bot/database/models/apartment.py",
}


def test_display_code_does_not_read_full_address_directly():
    """Гейт против возврата «показали канон как есть».

    Шесть call-site'ов расходились именно потому, что каждый брал
    `full_address` сам. Точечный фикс без гейта продержался бы до следующего
    экрана с адресом.
    """
    offenders = []
    for path in PACKAGE_ROOT.rglob("*.py"):
        rel = path.relative_to(PACKAGE_ROOT.parent).as_posix()
        if rel in FULL_ADDRESS_ALLOWED or "tests" in path.parts or "venv" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr == "full_address":
                offenders.append(f"{rel}:{node.lineno}")

    assert not offenders, (
        "прямое чтение `full_address` в коде показа — используйте "
        f"`address_helpers.apartment_address(apt, lang)`: {offenders}"
    )


@pytest.mark.asyncio
async def test_admin_notification_is_built_in_each_admin_language(
    session, apartment, monkeypatch
):
    """AUD5-CODE-12: два админа с разными языками — два разных текста."""
    from uk_management_bot.config import settings as settings_module
    from uk_management_bot.database import session as session_module
    from uk_management_bot.handlers import user_apartment_selection as uas

    session.add_all([
        User(id=1, telegram_id=APPLICANT, first_name="Ali", roles='["applicant"]',
             active_role="applicant", status="approved", language="uz"),
        User(id=2, telegram_id=RU_ADMIN, first_name="Admin RU", roles='["manager"]',
             active_role="manager", status="approved", language="ru"),
        User(id=3, telegram_id=UZ_ADMIN, first_name="Admin UZ", roles='["manager"]',
             active_role="manager", status="approved", language="uz"),
    ])
    session.commit()

    monkeypatch.setattr(session_module, "SessionLocal", lambda: session)
    monkeypatch.setattr(
        settings_module.settings, "ADMIN_USER_IDS", [RU_ADMIN, UZ_ADMIN], raising=False
    )

    bot = AsyncMock()
    await uas.send_apartment_request_notification(
        user_apartment_id=1,
        user_id=APPLICANT,
        apartment_id=apartment.id,  # вызывающий передаёт ID, а не готовый текст
        bot=bot,
    )

    sent = {call.args[0]: call.args[1] for call in bot.send_message.await_args_list}
    assert set(sent) == {RU_ADMIN, UZ_ADMIN}

    ru_text, uz_text = sent[RU_ADMIN], sent[UZ_ADMIN]
    locales = {
        lang: json.loads(
            (PACKAGE_ROOT / "config" / "locales" / f"{lang}.json").read_text("utf-8")
        )["user_apt_selection"]["handlers"]["admin_new_apartment_request"]
        for lang in ("ru", "uz")
    }
    ru_marker = locales["ru"].split("\n")[0]
    uz_marker = locales["uz"].split("\n")[0]

    assert ru_marker in ru_text, "RU-админ получил не русский шаблон"
    assert uz_marker in uz_text, "UZ-админ получил не узбекский шаблон (был хардкод 'ru')"
    assert "кв." in ru_text and "xon." in uz_text, (
        "адрес внутри уведомления должен быть на языке ПОЛУЧАТЕЛЯ, "
        f"а не заявителя: ru={ru_text!r} uz={uz_text!r}"
    )
