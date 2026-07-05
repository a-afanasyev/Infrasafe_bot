"""Тесты API складского учёта материалов (/api/v2/materials).

Покрытие по плану: CRUD номенклатуры (name UNIQUE навсегда), приход/партии,
FIFO-списание по нескольким партиям, запрет отрицательного остатка,
инвентаризационные корректировки и сторно (полное однократное сторно расхода
по исходным аллокациям; адресное сторно прихода мимо FIFO), snapshot имени,
живучесть журнала при удалении заявки, остатки, журнал операций, CSV,
by-request, procurement, RBAC.
"""
from contextlib import contextmanager
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.api.dependencies import get_current_user
from uk_management_bot.api.main import app
from uk_management_bot.database.models.material import (
    MaterialIssue,
    MaterialIssueAllocation,
    MaterialReceipt,
)
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.user import User

BASE = "/api/v2/materials"


def _d(value) -> Decimal:
    return Decimal(str(value))


@contextmanager
def _as_user(user: User):
    """Временно подменить текущего пользователя (поверх client-фикстуры)."""
    prev = app.dependency_overrides.get(get_current_user)

    async def override():
        return user

    app.dependency_overrides[get_current_user] = override
    try:
        yield
    finally:
        app.dependency_overrides[get_current_user] = prev


async def _mk_material(client: AsyncClient, name="Кабель ВВГ 3x2.5", unit="m",
                       min_stock=None) -> dict:
    body = {"name": name, "unit": unit}
    if min_stock is not None:
        body["min_stock"] = min_stock
    resp = await client.post(BASE, json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _mk_receipt(client: AsyncClient, material_id: int, qty, price,
                      **extra) -> dict:
    resp = await client.post(
        f"{BASE}/receipts",
        json={"material_id": material_id, "qty": qty, "unit_price": price, **extra},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _mk_request(db: AsyncSession, user: User,
                      number="260705-001", status="В работе") -> Request:
    req = Request(
        request_number=number,
        user_id=user.id,
        category="electrics",
        status=status,
        description="тестовая заявка",
        urgency="medium",
        address="test",
    )
    db.add(req)
    await db.commit()
    return req


# ── Номенклатура ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_material_crud_and_unique_name(client: AsyncClient):
    m = await _mk_material(client)
    assert m["unit"] == "m" and m["is_active"] is True

    dup = await client.post(BASE, json={"name": "Кабель ВВГ 3x2.5", "unit": "pcs"})
    assert dup.status_code == 409

    # имя занято НАВСЕГДА, даже после деактивации
    patch = await client.patch(f"{BASE}/{m['id']}", json={"is_active": False})
    assert patch.status_code == 200 and patch.json()["is_active"] is False
    dup2 = await client.post(BASE, json={"name": "Кабель ВВГ 3x2.5", "unit": "m"})
    assert dup2.status_code == 409
    assert "реактивируйте" in dup2.json()["detail"]

    listing = await client.get(BASE, params={"is_active": False})
    assert [row["id"] for row in listing.json()] == [m["id"]]


@pytest.mark.asyncio
async def test_material_bad_unit_rejected(client: AsyncClient):
    resp = await client.post(BASE, json={"name": "X", "unit": "шт"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_unit_change_forbidden_with_moves(client: AsyncClient):
    m = await _mk_material(client, name="Труба", unit="m")
    ok = await client.patch(f"{BASE}/{m['id']}", json={"unit": "pcs"})
    assert ok.status_code == 200  # движений нет — можно
    await _mk_receipt(client, m["id"], "5", "100.00")
    forbidden = await client.patch(f"{BASE}/{m['id']}", json={"unit": "kg"})
    assert forbidden.status_code == 409


# ── Приход / FIFO-списание ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_receipt_creates_batch(client: AsyncClient):
    m = await _mk_material(client)
    r = await _mk_receipt(client, m["id"], "10.5", "1000.00", supplier="ООО Стройка")
    assert _d(r["qty_remaining"]) == _d("10.5")
    assert _d(r["total_amount"]) == _d("10500.00")
    assert r["material_name"] == m["name"] and r["unit"] == m["unit"]


@pytest.mark.asyncio
async def test_issue_fifo_two_batches(client: AsyncClient, db_session: AsyncSession,
                                      manager_user: User):
    await _mk_request(db_session, manager_user)
    m = await _mk_material(client)
    r1 = await _mk_receipt(client, m["id"], "3", "100.00")
    r2 = await _mk_receipt(client, m["id"], "10", "150.00")

    resp = await client.post(f"{BASE}/issues", json={
        "material_id": m["id"], "qty": "5", "doc_type": "request",
        "request_number": "260705-001",
    })
    assert resp.status_code == 201, resp.text
    issue = resp.json()
    # 3×100 + 2×150 = 600
    assert _d(issue["total_cost"]) == _d("600.00")

    allocs = (await db_session.execute(
        select(MaterialIssueAllocation)
        .where(MaterialIssueAllocation.issue_id == issue["id"])
        .order_by(MaterialIssueAllocation.id)
    )).scalars().all()
    assert [(a.receipt_id, _d(a.qty), _d(a.amount)) for a in allocs] == [
        (r1["id"], _d("3"), _d("300.00")),
        (r2["id"], _d("2"), _d("300.00")),
    ]
    remaining = {
        r.id: _d(r.qty_remaining)
        for r in (await db_session.execute(select(MaterialReceipt))).scalars()
    }
    assert remaining[r1["id"]] == _d("0") and remaining[r2["id"]] == _d("8")


@pytest.mark.asyncio
async def test_issue_insufficient_stock_409(client: AsyncClient,
                                            db_session: AsyncSession,
                                            manager_user: User):
    await _mk_request(db_session, manager_user)
    m = await _mk_material(client)
    await _mk_receipt(client, m["id"], "2", "50.00")
    resp = await client.post(f"{BASE}/issues", json={
        "material_id": m["id"], "qty": "3", "doc_type": "request",
        "request_number": "260705-001",
    })
    assert resp.status_code == 409
    assert "2" in resp.json()["detail"]  # доступный остаток в сообщении


@pytest.mark.asyncio
async def test_issue_validation_matrix(client: AsyncClient,
                                       db_session: AsyncSession,
                                       manager_user: User):
    m = await _mk_material(client)
    await _mk_receipt(client, m["id"], "10", "10.00")

    # несуществующая заявка → 422
    resp = await client.post(f"{BASE}/issues", json={
        "material_id": m["id"], "qty": "1", "doc_type": "request",
        "request_number": "999999-999",
    })
    assert resp.status_code == 422

    # request без номера → 422
    resp = await client.post(f"{BASE}/issues", json={
        "material_id": m["id"], "qty": "1", "doc_type": "request",
    })
    assert resp.status_code == 422

    # household без причины → 422; с request_number → 422
    resp = await client.post(f"{BASE}/issues", json={
        "material_id": m["id"], "qty": "1", "doc_type": "household",
    })
    assert resp.status_code == 422
    resp = await client.post(f"{BASE}/issues", json={
        "material_id": m["id"], "qty": "1", "doc_type": "household",
        "reason": "уборка", "request_number": "260705-001",
    })
    assert resp.status_code == 422

    # household корректный → 201
    resp = await client.post(f"{BASE}/issues", json={
        "material_id": m["id"], "qty": "1", "doc_type": "household",
        "reason": "хознужды офиса",
    })
    assert resp.status_code == 201

    # shortage через /issues недоступен (схема Literal) → 422
    resp = await client.post(f"{BASE}/issues", json={
        "material_id": m["id"], "qty": "1", "doc_type": "shortage",
        "reason": "недостача",
    })
    assert resp.status_code == 422


# ── Корректировки: инвентаризация ───────────────────────────────────

@pytest.mark.asyncio
async def test_adjustment_inventory_surplus_and_shortage(client: AsyncClient):
    m = await _mk_material(client)
    resp = await client.post(f"{BASE}/adjustments", json={
        "material_id": m["id"], "direction": "surplus", "qty": "4",
        "unit_price": "25.00", "reason": "инвентаризация: излишек",
    })
    assert resp.status_code == 201
    receipts = resp.json()["receipts"]
    assert len(receipts) == 1 and receipts[0]["doc_type"] == "surplus"

    resp = await client.post(f"{BASE}/adjustments", json={
        "material_id": m["id"], "direction": "shortage", "qty": "1",
        "reason": "инвентаризация: недостача",
    })
    assert resp.status_code == 201
    issue = resp.json()["issue"]
    assert issue["doc_type"] == "shortage" and _d(issue["total_cost"]) == _d("25.00")

    # инвентаризация без qty → 422
    resp = await client.post(f"{BASE}/adjustments", json={
        "material_id": m["id"], "direction": "surplus", "reason": "x",
    })
    assert resp.status_code == 422


# ── Корректировки: сторно ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_reverse_issue_restores_batches_by_price(client: AsyncClient,
                                                       db_session: AsyncSession,
                                                       manager_user: User):
    """Сторно расхода из двух партий с разными ценами → две surplus-партии
    с исходными ценами (без средневзвешенного размытия)."""
    await _mk_request(db_session, manager_user)
    m = await _mk_material(client)
    await _mk_receipt(client, m["id"], "3", "100.00")
    await _mk_receipt(client, m["id"], "10", "150.00")
    issue = (await client.post(f"{BASE}/issues", json={
        "material_id": m["id"], "qty": "5", "doc_type": "request",
        "request_number": "260705-001",
    })).json()

    resp = await client.post(f"{BASE}/adjustments", json={
        "material_id": m["id"], "direction": "surplus",
        "reason": "ошибочное списание", "reversal_of_issue_id": issue["id"],
    })
    assert resp.status_code == 201, resp.text
    receipts = sorted(resp.json()["receipts"], key=lambda r: _d(r["unit_price"]))
    assert [( _d(r["qty"]), _d(r["unit_price"]), r["reversal_of_issue_id"])
            for r in receipts] == [
        (_d("3"), _d("100.00"), issue["id"]),
        (_d("2"), _d("150.00"), issue["id"]),
    ]

    # повторное сторно того же расхода → 409
    resp = await client.post(f"{BASE}/adjustments", json={
        "material_id": m["id"], "direction": "surplus",
        "reason": "повтор", "reversal_of_issue_id": issue["id"],
    })
    assert resp.status_code == 409

    # qty при сторно запрещён → 422
    resp = await client.post(f"{BASE}/adjustments", json={
        "material_id": m["id"], "direction": "surplus", "qty": "1",
        "reason": "x", "reversal_of_issue_id": issue["id"],
    })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_reverse_receipt_targets_exact_batch(client: AsyncClient,
                                                   db_session: AsyncSession):
    """Ключевой тест: сторно прихода списывает ИМЕННО указанную партию,
    даже при наличии более старой партии того же материала (мимо FIFO)."""
    m = await _mk_material(client)
    older = await _mk_receipt(client, m["id"], "5", "80.00")
    newer = await _mk_receipt(client, m["id"], "7", "90.00")

    resp = await client.post(f"{BASE}/adjustments", json={
        "material_id": m["id"], "direction": "shortage",
        "reason": "ошибочный приход", "reversal_of_receipt_id": newer["id"],
    })
    assert resp.status_code == 201, resp.text
    issue = resp.json()["issue"]
    assert issue["reversal_of_receipt_id"] == newer["id"]
    assert _d(issue["qty"]) == _d("7") and _d(issue["total_cost"]) == _d("630.00")

    allocs = (await db_session.execute(
        select(MaterialIssueAllocation)
        .where(MaterialIssueAllocation.issue_id == issue["id"])
    )).scalars().all()
    assert [a.receipt_id for a in allocs] == [newer["id"]]

    remaining = {
        r.id: _d(r.qty_remaining)
        for r in (await db_session.execute(select(MaterialReceipt))).scalars()
    }
    assert remaining[older["id"]] == _d("5")  # старая партия НЕ тронута
    assert remaining[newer["id"]] == _d("0")


@pytest.mark.asyncio
async def test_reverse_receipt_rejected_for_touched_batch(client: AsyncClient,
                                                          db_session: AsyncSession,
                                                          manager_user: User):
    await _mk_request(db_session, manager_user)
    m = await _mk_material(client)
    r = await _mk_receipt(client, m["id"], "5", "80.00")
    ok = await client.post(f"{BASE}/issues", json={
        "material_id": m["id"], "qty": "1", "doc_type": "request",
        "request_number": "260705-001",
    })
    assert ok.status_code == 201
    resp = await client.post(f"{BASE}/adjustments", json={
        "material_id": m["id"], "direction": "shortage",
        "reason": "сторно", "reversal_of_receipt_id": r["id"],
    })
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_reversal_compatibility_checks(client: AsyncClient,
                                             db_session: AsyncSession,
                                             manager_user: User):
    await _mk_request(db_session, manager_user)
    m1 = await _mk_material(client, name="Материал А")
    m2 = await _mk_material(client, name="Материал Б")
    r1 = await _mk_receipt(client, m1["id"], "5", "10.00")
    issue = (await client.post(f"{BASE}/issues", json={
        "material_id": m1["id"], "qty": "2", "doc_type": "request",
        "request_number": "260705-001",
    })).json()

    # surplus + reversal_of_receipt_id → 422
    resp = await client.post(f"{BASE}/adjustments", json={
        "material_id": m1["id"], "direction": "surplus",
        "reason": "x", "reversal_of_receipt_id": r1["id"],
    })
    assert resp.status_code == 422
    # shortage + reversal_of_issue_id → 422
    resp = await client.post(f"{BASE}/adjustments", json={
        "material_id": m1["id"], "direction": "shortage",
        "reason": "x", "reversal_of_issue_id": issue["id"],
    })
    assert resp.status_code == 422
    # material_id не совпадает с исходной операцией → 409
    resp = await client.post(f"{BASE}/adjustments", json={
        "material_id": m2["id"], "direction": "surplus",
        "reason": "x", "reversal_of_issue_id": issue["id"],
    })
    assert resp.status_code == 409
    # обе ссылки сразу → 422
    resp = await client.post(f"{BASE}/adjustments", json={
        "material_id": m1["id"], "direction": "surplus",
        "reason": "x", "reversal_of_issue_id": issue["id"],
        "reversal_of_receipt_id": r1["id"],
    })
    assert resp.status_code == 422


# ── Snapshot имени / живучесть журнала ─────────────────────────────

@pytest.mark.asyncio
async def test_rename_does_not_rewrite_history(client: AsyncClient):
    m = await _mk_material(client, name="Старое имя", unit="pcs")
    await _mk_receipt(client, m["id"], "1", "10.00")
    patch = await client.patch(f"{BASE}/{m['id']}", json={"name": "Новое имя"})
    assert patch.status_code == 200 and patch.json()["name"] == "Новое имя"

    ops = (await client.get(f"{BASE}/operations")).json()
    assert ops["items"][0]["material_name"] == "Старое имя"


@pytest.mark.asyncio
async def test_issue_journal_survives_request_delete(client: AsyncClient,
                                                     db_session: AsyncSession,
                                                     manager_user: User):
    req = await _mk_request(db_session, manager_user)
    m = await _mk_material(client)
    await _mk_receipt(client, m["id"], "5", "10.00")
    issue = (await client.post(f"{BASE}/issues", json={
        "material_id": m["id"], "qty": "2", "doc_type": "request",
        "request_number": req.request_number,
    })).json()

    await db_session.delete(req)
    await db_session.commit()

    alive = (await db_session.execute(
        select(MaterialIssue).where(MaterialIssue.id == issue["id"])
    )).scalar_one_or_none()
    assert alive is not None
    assert alive.request_number == "260705-001"  # «висячий» номер допустим


# ── Остатки / журнал / отчёты ───────────────────────────────────────

@pytest.mark.asyncio
async def test_stock_aggregate_and_low_flag(client: AsyncClient):
    m1 = await _mk_material(client, name="Мало на складе", min_stock="10")
    m2 = await _mk_material(client, name="Хватает", min_stock="1")
    m3 = await _mk_material(client, name="Без порога")
    await _mk_receipt(client, m1["id"], "4", "100.00")
    await _mk_receipt(client, m2["id"], "5", "50.00")
    await _mk_receipt(client, m3["id"], "1", "10.00")

    rows = {r["name"]: r for r in (await client.get(f"{BASE}/stock")).json()}
    assert _d(rows["Мало на складе"]["stock"]) == _d("4")
    assert _d(rows["Мало на складе"]["stock_value"]) == _d("400.00")
    assert rows["Мало на складе"]["low_stock"] is True
    assert rows["Хватает"]["low_stock"] is False
    assert rows["Без порога"]["low_stock"] is False

    low = (await client.get(f"{BASE}/stock", params={"only_low": True})).json()
    assert [r["name"] for r in low] == ["Мало на складе"]


@pytest.mark.asyncio
async def test_operations_filters_and_pagination(client: AsyncClient,
                                                 db_session: AsyncSession,
                                                 manager_user: User):
    await _mk_request(db_session, manager_user)
    m = await _mk_material(client)
    await _mk_receipt(client, m["id"], "10", "10.00")
    for _ in range(3):
        resp = await client.post(f"{BASE}/issues", json={
            "material_id": m["id"], "qty": "1", "doc_type": "request",
            "request_number": "260705-001",
        })
        assert resp.status_code == 201

    all_ops = (await client.get(f"{BASE}/operations")).json()
    assert all_ops["total"] == 4

    issues_only = (await client.get(
        f"{BASE}/operations", params={"op_type": "issue"})).json()
    assert issues_only["total"] == 3
    assert all(op["op_type"] == "issue" for op in issues_only["items"])

    by_request = (await client.get(
        f"{BASE}/operations", params={"request_number": "260705-001"})).json()
    assert by_request["total"] == 3

    page = (await client.get(
        f"{BASE}/operations", params={"limit": 2, "offset": 2})).json()
    assert page["total"] == 4 and len(page["items"]) == 2


@pytest.mark.asyncio
async def test_operations_csv_export(client: AsyncClient):
    m = await _mk_material(client)
    await _mk_receipt(client, m["id"], "2", "99.00", supplier="ИП Ремонт")
    resp = await client.get(f"{BASE}/operations/export")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    body = resp.text
    assert body.startswith("﻿")  # BOM для Excel
    lines = body.lstrip("﻿").splitlines()
    assert lines[0].split(";")[0] == "Тип"
    assert "Приход" in lines[1] and "ИП Ремонт" in lines[1]


@pytest.mark.asyncio
async def test_by_request_report(client: AsyncClient, db_session: AsyncSession,
                                 manager_user: User):
    await _mk_request(db_session, manager_user)
    m = await _mk_material(client)
    await _mk_receipt(client, m["id"], "10", "100.00")
    for qty in ("2", "3"):
        await client.post(f"{BASE}/issues", json={
            "material_id": m["id"], "qty": qty, "doc_type": "request",
            "request_number": "260705-001",
        })
    report = (await client.get(f"{BASE}/by-request/260705-001")).json()
    assert len(report["items"]) == 2
    assert _d(report["total_cost"]) == _d("500.00")


@pytest.mark.asyncio
async def test_procurement_deficit_and_open_requests(client: AsyncClient,
                                                     db_session: AsyncSession,
                                                     manager_user: User):
    await _mk_request(db_session, manager_user, number="260705-002",
                      status="Закуп")
    req = (await db_session.execute(
        select(Request).where(Request.request_number == "260705-002")
    )).scalar_one()
    req.requested_materials = "гвозди 100шт, краска 2л"
    await db_session.commit()

    deficit_m = await _mk_material(client, name="Дефицитный", min_stock="10")
    ok_m = await _mk_material(client, name="Достаточный", min_stock="1")
    no_min_m = await _mk_material(client, name="Без min_stock")
    await _mk_receipt(client, deficit_m["id"], "3", "10.00")
    await _mk_receipt(client, ok_m["id"], "5", "10.00")
    await _mk_receipt(client, no_min_m["id"], "0.5", "10.00")

    data = (await client.get(f"{BASE}/procurement")).json()
    assert [r["name"] for r in data["deficit"]] == ["Дефицитный"]
    assert _d(data["deficit"][0]["to_buy"]) == _d("7")
    assert data["open_purchase_requests"][0]["request_number"] == "260705-002"
    assert "гвозди" in data["open_purchase_requests"][0]["requested_materials"]

    csv_resp = await client.get(f"{BASE}/procurement/export")
    assert csv_resp.status_code == 200
    assert "Дефицитный" in csv_resp.text


# ── RBAC ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_rbac_executor_forbidden(client: AsyncClient,
                                       db_session: AsyncSession):
    executor = User(
        telegram_id=777777, username="exec", first_name="Exec",
        roles='["executor"]', active_role="executor", status="approved",
    )
    db_session.add(executor)
    await db_session.commit()
    await db_session.refresh(executor)

    with _as_user(executor):
        for method, path, body in [
            ("GET", BASE, None),
            ("GET", f"{BASE}/stock", None),
            ("POST", f"{BASE}/receipts",
             {"material_id": 1, "qty": "1", "unit_price": "1"}),
            ("GET", f"{BASE}/operations", None),
            ("GET", f"{BASE}/procurement", None),
        ]:
            resp = await (client.get(path) if method == "GET"
                          else client.post(path, json=body))
            assert resp.status_code == 403, f"{method} {path}: {resp.status_code}"


# ── Инвариант qty_remaining = qty − SUM(allocations) ────────────────

@pytest.mark.asyncio
async def test_qty_remaining_invariant_after_series(client: AsyncClient,
                                                    db_session: AsyncSession,
                                                    manager_user: User):
    await _mk_request(db_session, manager_user)
    m = await _mk_material(client)
    await _mk_receipt(client, m["id"], "5", "10.00")
    await _mk_receipt(client, m["id"], "5", "20.00")
    issue = (await client.post(f"{BASE}/issues", json={
        "material_id": m["id"], "qty": "7", "doc_type": "request",
        "request_number": "260705-001",
    })).json()
    await client.post(f"{BASE}/adjustments", json={
        "material_id": m["id"], "direction": "surplus",
        "reason": "сторно", "reversal_of_issue_id": issue["id"],
    })
    await client.post(f"{BASE}/adjustments", json={
        "material_id": m["id"], "direction": "shortage", "qty": "1",
        "reason": "недостача",
    })

    receipts = (await db_session.execute(select(MaterialReceipt))).scalars().all()
    for r in receipts:
        allocated = sum(
            (_d(a.qty) for a in (await db_session.execute(
                select(MaterialIssueAllocation)
                .where(MaterialIssueAllocation.receipt_id == r.id)
            )).scalars()),
            Decimal("0"),
        )
        assert _d(r.qty_remaining) == _d(r.qty) - allocated, f"receipt {r.id}"
