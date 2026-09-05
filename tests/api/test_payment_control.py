import contextlib
import json
from unittest.mock import AsyncMock

import pytest

pytestmark = pytest.mark.asyncio
BASE = "/api/v2/addresses"


async def apartment(client, account="001", number="1"):
    yard = (await client.post(f"{BASE}/yards", json={"name": "Payment Yard"})).json()
    building = (await client.post(f"{BASE}/buildings", json={"yard_id": yard["id"], "address": "Payment street 1"})).json()
    return await client.post(f"{BASE}/apartments", json={"building_id": building["id"], "apartment_number": number, "account_number": account})


async def test_account_roundtrip_clear_and_unique(client):
    result = await apartment(client, " 001 ")
    assert result.status_code == 201, result.text
    apt = result.json()
    assert apt["account_number"] == "001"
    assert (await client.get(f"{BASE}/apartments/{apt['id']}")).json()["account_number"] == "001"
    duplicate = await client.post(f"{BASE}/apartments", json={"building_id": apt["building_id"], "apartment_number": "2", "account_number": "001"})
    assert duplicate.status_code == 409
    cleared = await client.patch(f"{BASE}/apartments/{apt['id']}", json={"account_number": ""})
    assert cleared.json()["account_number"] is None


async def test_apartment_balance_no_account_does_not_call_service(client, monkeypatch):
    from uk_management_bot.api.payment_control import router as module
    mock = AsyncMock()
    monkeypatch.setattr(module, "service_request", mock)
    apt = (await apartment(client, None)).json()
    result = await client.get(f"/api/v2/payment-control/apartments/{apt['id']}")
    assert result.json()["status"] == "no_account"
    mock.assert_not_called()


async def test_apartment_balance_uses_saved_account_and_unavailable_is_not_zero(client, monkeypatch):
    from fastapi import HTTPException
    from uk_management_bot.api.payment_control import router as module
    apt = (await apartment(client)).json()
    mock = AsyncMock(return_value={"status": "available", "account_number": "001", "current": {"debt": "100.00", "prepayment": "0.00", "as_of": "2026-09-01"}})
    monkeypatch.setattr(module, "service_request", mock)
    result = await client.get(f"/api/v2/payment-control/apartments/{apt['id']}")
    assert result.json()["current"]["debt"] == "100.00"
    assert mock.call_args.kwargs["params"]["account_number"] == "001"
    mock.side_effect = HTTPException(503, "unavailable")
    result = await client.get(f"/api/v2/payment-control/apartments/{apt['id']}")
    assert result.json()["status"] == "unavailable"
    assert result.json()["current"] is None


@pytest.mark.parametrize('method,path,payload', [
    ('get', '/imports', None), ('get', '/imports/12?offset=200', None),
    ('get', '/account?account_number=001', None),
    ('post', '/imports/12/activate', None),
    ('post', '/imports/12/deactivate', {'reason': 'Wrong file'}),
])
async def test_gateway_routes(client, monkeypatch, method, path, payload):
    from uk_management_bot.api.payment_control import router as module
    mock = AsyncMock(return_value={'ok': True})
    monkeypatch.setattr(module, 'service_request', mock)
    kwargs = {'json': payload} if payload else {}
    result = await getattr(client, method)('/api/v2/payment-control' + path, **kwargs)
    assert result.status_code == 200
    assert mock.call_args.args[2].id is not None


async def test_gateway_preview_and_upload_limit(client, monkeypatch):
    from uk_management_bot.api.payment_control import router as module
    mock = AsyncMock(return_value={'id': 1})
    monkeypatch.setattr(module, 'service_request', mock)
    response = await client.post('/api/v2/payment-control/imports/preview', data={'kind': 'balances', 'as_of': '2026-09-01', 'source': 'Accounting'}, files={'file': ('x.csv', b'hello')})
    assert response.status_code == 200
    assert mock.call_args.kwargs['files']['file'][1] == b'hello'
    response = await client.post('/api/v2/payment-control/imports/preview', data={'kind': 'balances', 'as_of': '2026-09-01', 'source': 'Accounting'}, files={'file': ('x.csv', b'x' * (module.MAX_BYTES + 1))})
    assert response.status_code == 413


async def test_gateway_resident_cannot_read_financial_data(client, resident_user):
    async with acting_as(resident_user):
        response = await client.get('/api/v2/payment-control/account?account_number=001')
    assert response.status_code == 403


async def test_service_transport_credentials_and_error_mapping(monkeypatch, manager_user):
    import httpx
    from fastapi import HTTPException
    from uk_management_bot.api.payment_control import router as module
    monkeypatch.setattr(module.settings, 'PAYMENT_SERVICE_TOKEN', '')
    with pytest.raises(HTTPException) as err:
        await module.service_request('GET', '/imports', manager_user)
    assert err.value.status_code == 503
    monkeypatch.setattr(module.settings, 'PAYMENT_SERVICE_TOKEN', 'test-server-token')
    original_client = httpx.AsyncClient
    for code in [200, 409, 401, 500]:
        def handler(request):
            assert request.headers['X-Service-Token'] == 'test-server-token'
            assert request.headers['X-Actor-Id'] == str(manager_user.id)
            return httpx.Response(code, json={'detail': 'test-error', 'ok': True})
        monkeypatch.setattr(module.httpx, 'AsyncClient', lambda **kwargs: original_client(transport=httpx.MockTransport(handler)))
        if code == 200:
            assert (await module.service_request('GET', '/imports', manager_user))['ok']
        else:
            with pytest.raises(HTTPException) as err:
                await module.service_request('GET', '/imports', manager_user)
            assert err.value.status_code == (409 if code == 409 else 503)


# ── Правки по итогам ревью ───────────────────────────────────────────────────

@contextlib.asynccontextmanager
async def acting_as(user):
    """Подмена личности с восстановлением: незакрытый override протекал бы в
    следующий тест, который не пользуется фикстурой `client`."""
    from uk_management_bot.api.main import app
    from uk_management_bot.api.dependencies import get_current_user
    previous = app.dependency_overrides.get(get_current_user)
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        yield
    finally:
        if previous is None:
            app.dependency_overrides.pop(get_current_user, None)
        else:
            app.dependency_overrides[get_current_user] = previous


async def make_user(db_session, telegram_id, roles, status="approved"):
    from uk_management_bot.database.models.user import User
    user = User(telegram_id=telegram_id, username=f"u{telegram_id}", first_name="T", last_name="U",
                roles=roles, active_role=json.loads(roles)[0], status=status)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


PAYMENT_ROUTES = [
    ("get", "/imports", None),
    ("get", "/imports/12", None),
    ("get", "/account?account_number=001", None),
    ("get", "/apartments/1", None),
    ("post", "/imports/12/activate", None),
    ("post", "/imports/12/deactivate", {"reason": "Wrong file"}),
]


@pytest.mark.parametrize("method,path,payload", PAYMENT_ROUTES)
@pytest.mark.parametrize("roles,status", [
    ('["executor"]', "approved"),
    ('["applicant"]', "approved"),
    ('["manager"]', "pending"),
])
async def test_all_payment_routes_require_approved_staff(client, db_session, monkeypatch, method, path, payload, roles, status):
    """Финансовые данные закрыты для исполнителя, жителя и неодобренного менеджера
    на КАЖДОМ роуте раздела, а не только на /account."""
    from uk_management_bot.api.payment_control import router as module
    mock = AsyncMock(return_value={"ok": True})
    monkeypatch.setattr(module, "service_request", mock)
    user = await make_user(db_session, 700000 + abs(hash((roles, status, path))) % 90000, roles, status)
    kwargs = {"json": payload} if payload else {}
    async with acting_as(user):
        response = await getattr(client, method)("/api/v2/payment-control" + path, **kwargs)
    assert response.status_code == 403, response.text
    mock.assert_not_called()


async def test_preview_route_requires_approved_staff(client, db_session, monkeypatch):
    from uk_management_bot.api.payment_control import router as module
    mock = AsyncMock(return_value={"id": 1})
    monkeypatch.setattr(module, "service_request", mock)
    user = await make_user(db_session, 777001, '["executor"]')
    async with acting_as(user):
        response = await client.post("/api/v2/payment-control/imports/preview",
                                    data={"kind": "balances", "as_of": "2026-09-01", "source": "Accounting"},
                                    files={"file": ("x.csv", b"hello")})
    assert response.status_code == 403
    mock.assert_not_called()


async def test_account_number_unique_against_inactive_apartment(client):
    """Уникальность считается по всей инсталляции, включая деактивированные
    квартиры: иначе счёт «висел» бы на двух записях одновременно."""
    apt = (await apartment(client, "555001", number="10")).json()
    assert (await client.delete(f"{BASE}/apartments/{apt['id']}")).status_code == 200
    duplicate = await client.post(f"{BASE}/apartments", json={
        "building_id": apt["building_id"], "apartment_number": "11", "account_number": "555001"})
    assert duplicate.status_code == 409
    assert "10" in duplicate.json()["detail"]


async def test_account_number_format_boundaries_on_write(client):
    apt = (await apartment(client, "9" * 64, number="20")).json()
    assert apt["account_number"] == "9" * 64
    too_long = await client.patch(f"{BASE}/apartments/{apt['id']}", json={"account_number": "9" * 65})
    assert too_long.status_code == 422
    cyrillic = await client.patch(f"{BASE}/apartments/{apt['id']}", json={"account_number": "00О1"})
    assert cyrillic.status_code == 422
    spaced = await client.patch(f"{BASE}/apartments/{apt['id']}", json={"account_number": "  770123  "})
    assert spaced.json()["account_number"] == "770123"


async def test_conflict_message_names_the_holding_apartment(client):
    first = (await apartment(client, "660001", number="30")).json()
    conflict = await client.post(f"{BASE}/apartments", json={
        "building_id": first["building_id"], "apartment_number": "31", "account_number": "660001"})
    assert conflict.status_code == 409
    detail = conflict.json()["detail"]
    assert "30" in detail and "Payment street 1" in detail


async def test_apartment_balance_validation_error_is_not_masked_as_unavailable(client, monkeypatch):
    """422 от сервиса — это «неверный счёт», и он не должен выглядеть как «сервис недоступен»."""
    from fastapi import HTTPException
    from uk_management_bot.api.payment_control import router as module
    apt = (await apartment(client, "440001", number="40")).json()
    monkeypatch.setattr(module, "service_request",
                        AsyncMock(side_effect=HTTPException(422, "Некорректный лицевой счёт")))
    response = await client.get(f"/api/v2/payment-control/apartments/{apt['id']}")
    assert response.status_code == 422
    assert response.json()["detail"] == "Некорректный лицевой счёт"
