"""BUG: «не работает выдача приглашений» — POST /api/v2/shifts/employees/invite → 500.

Прод (profk, 2026-08-17): 7 подряд 500 с одним трейсом —
`ValueError: Specialization is required for executor role` из
`InviteService.generate_invite`, вылетавший НЕизловленным из хендлера.

Правило само по себе продуктовое (в боте специализацию спрашивают FSM-шагом),
но веб-модалка позволяла отправить executor с пустым списком, а ошибка ввода
превращалась в 500 без текста — менеджер видел «не работает».

Здесь фиксируем контракт API: невалидный ввод → 422 с внятным detail,
причём БЕЗ похода в сеть (getMe) и в БД.
"""
import pytest
from fastapi import HTTPException

from uk_management_bot.api.shifts.router import employees as employees_mod
from uk_management_bot.api.shifts.schemas import CreateInviteRequest


class _Actor:
    telegram_id = 5000000001


#: Маркер «внутренней подробности» в тексте исключения сервиса — проверяем, что
#: он не доезжает до клиента (см. тест на generic-перехват).
_SECRETISH = "internal-detail-must-not-leak"


@pytest.mark.asyncio
async def test_executor_without_specialization_is_422_not_500(monkeypatch):
    """executor + пустые специализации → 422, а не ValueError/500."""

    async def _boom():
        raise AssertionError("невалидный ввод не должен доходить до getMe()")

    monkeypatch.setattr(employees_mod, "_resolve_bot_username", _boom)

    body = CreateInviteRequest(role="executor", specializations=[], hours=24)

    with pytest.raises(HTTPException) as exc:
        await employees_mod.create_invite(body=body, db=None, current_user=_Actor())

    assert exc.value.status_code == 422
    assert "specialization" in str(exc.value.detail).lower()


@pytest.mark.asyncio
async def test_manager_without_specialization_still_works(monkeypatch):
    """Гвард не должен задеть manager-инвайт: специализация ему не нужна."""
    import uk_management_bot.database.session as session_mod
    import uk_management_bot.services.invite_service as invite_mod

    async def _username():
        return "profkbot"

    class _FakeSession:
        def close(self):
            pass

    class _FakeInviteService:
        def __init__(self, db):
            pass

        def generate_invite(self, role, created_by, specialization=None, hours=24):
            assert role == "manager"
            assert specialization is None
            return "invite_v1:ok.sig"

    monkeypatch.setattr(employees_mod, "_resolve_bot_username", _username)
    monkeypatch.setattr(session_mod, "SessionLocal", lambda: _FakeSession())
    monkeypatch.setattr(invite_mod, "InviteService", _FakeInviteService)

    body = CreateInviteRequest(role="manager", specializations=[], hours=24)
    resp = await employees_mod.create_invite(body=body, db=None, current_user=_Actor())

    assert resp.token == "invite_v1:ok.sig"
    assert resp.bot_link == "https://t.me/profkbot"


@pytest.mark.asyncio
async def test_service_value_error_maps_to_422_without_echoing_message(monkeypatch):
    """Любой ValueError валидации из сервиса — 422, а не 500 (сеть безопасности).

    И текст исключения НЕ пересылается клиенту: перехват generic, будущая
    проверка может положить в сообщение внутреннее состояние, а `detail`
    доезжает до тоста в браузере (`safeErrorMessage` отдаёт строку как есть).
    """
    import uk_management_bot.database.session as session_mod
    import uk_management_bot.services.invite_service as invite_mod

    async def _username():
        return "profkbot"

    class _FakeSession:
        def close(self):
            pass

    class _FakeInviteService:
        def __init__(self, db):
            pass

        def generate_invite(self, **kwargs):
            raise ValueError(f"row id=42 conflicts with {_SECRETISH}")

    monkeypatch.setattr(employees_mod, "_resolve_bot_username", _username)
    monkeypatch.setattr(session_mod, "SessionLocal", lambda: _FakeSession())
    monkeypatch.setattr(invite_mod, "InviteService", _FakeInviteService)

    body = CreateInviteRequest(role="executor", specializations=["plumber"], hours=24)

    with pytest.raises(HTTPException) as exc:
        await employees_mod.create_invite(body=body, db=None, current_user=_Actor())

    assert exc.value.status_code == 422
    assert _SECRETISH not in str(exc.value.detail)


@pytest.mark.asyncio
async def test_guard_follows_service_predicate_not_its_own_copy(monkeypatch):
    """Гвард роутера обязан спрашивать предикат сервиса, а не повторять условие.

    Если правило когда-нибудь сменится (владелец рассматривает инвайт
    исполнителя без специализации), одна правка в `invite_service` должна
    отпускать и API. Собственная копия условия в роутере тихо разъехалась бы.
    """
    import uk_management_bot.database.session as session_mod
    import uk_management_bot.services.invite_service as invite_mod

    async def _username():
        return "profkbot"

    class _FakeSession:
        def close(self):
            pass

    class _FakeInviteService:
        def __init__(self, db):
            pass

        def generate_invite(self, **kwargs):
            return "invite_v1:ok.sig"

    monkeypatch.setattr(employees_mod, "_resolve_bot_username", _username)
    monkeypatch.setattr(session_mod, "SessionLocal", lambda: _FakeSession())
    monkeypatch.setattr(invite_mod, "InviteService", _FakeInviteService)
    # Правило «отпустили»: специализация больше не обязательна ни для кого.
    monkeypatch.setattr(invite_mod, "requires_specialization", lambda role: False)

    body = CreateInviteRequest(role="executor", specializations=[], hours=24)
    resp = await employees_mod.create_invite(body=body, db=None, current_user=_Actor())

    assert resp.token == "invite_v1:ok.sig"


@pytest.mark.asyncio
async def test_missing_invite_secret_is_not_downgraded_to_422(monkeypatch):
    """Сбой КОНФИГУРАЦИИ остаётся 500 и не уезжает клиенту как ошибка ввода.

    Конструктор InviteService бросает ValueError при пустом INVITE_SECRET.
    Если бы 422 ловил любой ValueError, менеджер получил бы «невалидный ввод»
    вместе с именем переменной окружения вместо честного отказа сервера.
    """
    import uk_management_bot.database.session as session_mod
    import uk_management_bot.services.invite_service as invite_mod

    async def _username():
        return "profkbot"

    class _FakeSession:
        def close(self):
            pass

    class _MisconfiguredInviteService:
        def __init__(self, db):
            raise ValueError("INVITE_SECRET must be set in environment variables")

    monkeypatch.setattr(employees_mod, "_resolve_bot_username", _username)
    monkeypatch.setattr(session_mod, "SessionLocal", lambda: _FakeSession())
    monkeypatch.setattr(invite_mod, "InviteService", _MisconfiguredInviteService)

    body = CreateInviteRequest(role="manager", specializations=[], hours=24)

    with pytest.raises(ValueError) as exc:
        await employees_mod.create_invite(body=body, db=None, current_user=_Actor())

    assert not isinstance(exc.value, HTTPException)
