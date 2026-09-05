import io

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook

from payment_control.app import create_app


@pytest.fixture
def client(tmp_path):
    app = create_app(f"sqlite:///{tmp_path / 'payments.db'}", "test-token-123456789012345678901234", initialize=True)
    with TestClient(app, headers={"X-Service-Token": "test-token-123456789012345678901234", "X-Actor-Id": "7"}) as c:
        yield c


def preview(client, text, kind="balances", as_of="2026-09-01"):
    return client.post("/v1/imports/preview", data={"kind": kind, "as_of": as_of, "source": "Accounting"},
                       files={"file": ("report.csv", text.encode(), "text/csv")})


def activate(client, response):
    assert response.status_code == 200, response.text
    result = client.post(f"/v1/imports/{response.json()['id']}/activate")
    assert result.status_code == 200, result.text
    return result.json()


def balance(client, account="001"):
    return client.get("/v1/account", params={"account_number": account}).json()


def test_preview_activation_and_missing_are_distinct(client):
    report = preview(client, "account_number;debt;prepayment\n001;120,50;0\n002;0;300\n")
    assert balance(client)["status"] == "no_data"
    activate(client, report)
    assert balance(client)["current"]["debt"] == "120.50"
    assert balance(client, "002")["current"]["prepayment"] == "300.00"
    assert balance(client, "missing")["status"] == "no_data"


def test_effective_date_not_upload_order_and_deactivation(client):
    old = preview(client, "account_number;debt;prepayment\n001;100;0\n", as_of="2026-08-01")
    new = preview(client, "account_number;debt;prepayment\n001;0;50\n")
    activate(client, new)
    activate(client, old)
    assert balance(client)["current"]["prepayment"] == "50.00"
    assert client.post(f"/v1/imports/{new.json()['id']}/deactivate", json={"reason": "Wrong export"}).status_code == 200
    assert balance(client)["current"]["debt"] == "100.00"


def test_duplicate_file_is_idempotent_and_missing_row_preserves_previous(client):
    text = "account_number;debt;prepayment\n001;20;0\n"
    first = preview(client, text)
    activate(client, first)
    assert preview(client, text).json()["id"] == first.json()["id"]
    activate(client, preview(client, "account_number;debt;prepayment\n002;0;0\n", as_of="2026-09-02"))
    assert balance(client)["current"]["as_of"] == "2026-09-01"


@pytest.mark.parametrize("text", [
    "account_number;debt;prepayment\n001;NaN;0\n",
    "account_number;debt;prepayment\n001;-1;0\n",
    "account_number;debt;prepayment\n001;1.001;0\n",
    "account_number;debt;prepayment\n001;1;0\n001;2;0\n",
    "account_number;debt;prepayment\n001;;\n",
])
def test_bad_rows_cannot_be_activated(client, text):
    report = preview(client, text)
    assert report.status_code == 200
    assert report.json()["invalid"] > 0
    assert client.post(f"/v1/imports/{report.json()['id']}/activate").status_code == 422


def test_payments_do_not_subtract_snapshot_and_overlap_is_rejected(client):
    activate(client, preview(client, "account_number;debt;prepayment\n001;100;0\n"))
    text = "account_number;operation_id;paid_at;amount\n001;bank-1;2026-09-02;30\n"
    activate(client, preview(client, text, kind="payments"))
    account = balance(client)
    assert account["current"]["debt"] == "100.00"
    assert account["payments"][0]["amount"] == "30.00"
    overlap = preview(client, text + "001;bank-2;2026-09-03;10\n", kind="payments")
    assert client.post(f"/v1/imports/{overlap.json()['id']}/activate").status_code == 409


def test_xlsx_leading_zero_text_and_formula_rejected(client):
    for value, valid in [("15", True), ("=10+5", False)]:
        wb = Workbook()
        wb.active.append(["account_number", "debt", "prepayment"])
        wb.active.append(["001", value, 0])
        stream = io.BytesIO()
        wb.save(stream)
        response = client.post("/v1/imports/preview", data={"kind": "balances", "as_of": "2026-09-01", "source": "XLSX"}, files={"file": ("data.xlsx", stream.getvalue())})
        assert response.status_code == 200
        assert (response.json()["invalid"] == 0) is valid


def test_auth_and_audit(client):
    assert client.get("/v1/imports", headers={"X-Service-Token": "wrong"}).status_code == 401
    report = preview(client, "account_number;debt;prepayment\n001;0;0\n")
    activate(client, report)
    audit = client.get(f"/v1/imports/{report.json()['id']}").json()["audit"]
    assert [event["action"] for event in audit] == ["preview", "activate"]
    assert audit[-1]["actor_id"] == "7"


def test_migrations_and_health(tmp_path, monkeypatch):
    from alembic import command
    from alembic.config import Config
    from payment_control.database import database_url
    url = f"sqlite:///{tmp_path / 'migrations.db'}"
    monkeypatch.setenv("PAYMENT_DATABASE_URL", url)
    assert database_url() == url
    config = Config("payment_control/alembic.ini")
    command.upgrade(config, "head")
    command.check(config)
    with TestClient(create_app(url, "test-token-123456789012345678901234")) as c:
        assert c.get('/health').status_code == 200
    command.downgrade(config, "base")


def test_invalid_upload_and_account(client):
    for filename, content in [("data.xlsm", b"x"), ("data.xlsx", b"corrupt"), ("empty.csv", b""), ("data.csv", b"a;a\n1;2")]:
        response = client.post("/v1/imports/preview", data={"kind": "balances", "as_of": "2026-09-01", "source": "Accounting"}, files={"file": (filename, content)})
        assert response.status_code == 422
    assert client.get('/v1/account', params={'account_number': '../bad'}).status_code == 422
    assert client.get('/v1/imports/99999').status_code == 404
    assert client.get('/v1/imports', headers={'X-Actor-Id': ''}).status_code == 400


def test_reactivation_and_same_date_correction(client):
    first = preview(client, "account_number;debt;prepayment\n001;50;0\n")
    activate(client, first)
    second = preview(client, "account_number;debt;prepayment\n001;40;0\n")
    activate(client, second)
    activate(client, first)
    assert balance(client)['current']['debt'] == '40.00'
    assert client.post(f"/v1/imports/{second.json()['id']}/deactivate", json={'reason': '   '}).status_code == 422
    assert client.get('/v1/imports').json()[0]['status'] == 'active'


def test_runtime_database_password_is_escaped(monkeypatch):
    from payment_control.database import database_url
    monkeypatch.delenv('PAYMENT_DATABASE_URL', raising=False)
    monkeypatch.setenv('PAYMENT_DB_PASSWORD', 'test:@/?')
    url = database_url()
    assert url.password == 'test:@/?'
    assert url.username == 'payment_app'


def test_source_row_after_first_page_and_blank_lines(client):
    rows = ''.join(f'{i:04d};0;10\n' for i in range(201))
    report = preview(client, 'account_number;debt;prepayment\n\n' + rows)
    activate(client, report)
    current = balance(client, '0200')['current']
    assert current['position'] == 200
    assert current['line'] == 203
    page = client.get(f"/v1/imports/{report.json()['id']}?offset=200").json()
    assert page['rows'][0]['account_number'] == '0200'


# ── Краевые случаи и правки по итогам ревью ────────────────────────────────────

def upload(client, filename, content, kind="balances", as_of="2026-09-01", source="Accounting"):
    return client.post("/v1/imports/preview", data={"kind": kind, "as_of": as_of, "source": source},
                       files={"file": (filename, content)})


def xlsx_bytes(rows):
    workbook = Workbook()
    for row in rows:
        workbook.active.append(row)
    stream = io.BytesIO()
    workbook.save(stream)
    return stream.getvalue()


def test_bom_only_csv_is_rejected_as_empty(client):
    """Excel сохраняет пустой лист как три байта BOM — раньше это был IndexError и 500."""
    response = upload(client, "empty.csv", b"\xef\xbb\xbf")
    assert response.status_code == 422
    assert "пуст" in response.json()["detail"]


def test_windows1251_and_bom_csv_with_russian_headers(client):
    russian = "Лицевой счёт;Долг;Предоплата\n001;10;0\n"
    assert upload(client, "cp1251.csv", russian.encode("cp1251")).json()["invalid"] == 0
    bom = upload(client, "bom.csv", b"\xef\xbb\xbf" + russian.encode("utf-8"))
    assert bom.json()["invalid"] == 0
    assert bom.json()["rows"][0]["account_number"] == "001"


def test_comma_delimited_csv(client):
    report = upload(client, "commas.csv", b"account_number,debt,prepayment\n001,10,0\n")
    assert report.json()["invalid"] == 0
    assert report.json()["rows"][0]["debt"] == "10.00"


def test_xlsx_numeric_account_cell_is_rejected(client):
    """Лицевой счёт обязан быть текстом: числовая ячейка теряет начальные нули."""
    numeric = upload(client, "numeric.xlsx", xlsx_bytes([["account_number", "debt", "prepayment"], [1, 10, 0]]))
    assert numeric.json()["invalid"] == 1
    text = upload(client, "text.xlsx", xlsx_bytes([["account_number", "debt", "prepayment"], ["001", 10, 0]]))
    assert text.json()["invalid"] == 0


def test_payment_date_formats(client):
    from datetime import datetime
    dotted = upload(client, "dotted.csv", b"account_number;operation_id;paid_at;amount\n001;a-1;05.09.2026;10\n", kind="payments")
    assert dotted.json()["invalid"] == 0
    assert dotted.json()["rows"][0]["paid_at"] == "2026-09-05"
    excel = upload(client, "excel.xlsx", xlsx_bytes([["account_number", "operation_id", "paid_at", "amount"],
                                                     ["001", "a-2", datetime(2026, 9, 4), 10]]), kind="payments")
    assert excel.json()["invalid"] == 0
    assert excel.json()["rows"][0]["paid_at"] == "2026-09-04"
    garbage = upload(client, "bad.csv", b"account_number;operation_id;paid_at;amount\n001;a-3;yesterday;10\n", kind="payments")
    assert garbage.json()["invalid"] == 1


def test_zero_payment_amount_is_rejected(client):
    zero = upload(client, "zero.csv", b"account_number;operation_id;paid_at;amount\n001;a-1;2026-09-01;0\n", kind="payments")
    assert zero.json()["invalid"] == 1
    positive = upload(client, "ok.csv", b"account_number;operation_id;paid_at;amount\n001;a-2;2026-09-01;0.01\n", kind="payments")
    assert positive.json()["invalid"] == 0


def test_account_number_length_and_alphabet_boundaries(client):
    fits = upload(client, "fits.csv", f"account_number;debt;prepayment\n{'9' * 64};10;0\n".encode())
    assert fits.json()["invalid"] == 0
    too_long = upload(client, "long.csv", f"account_number;debt;prepayment\n{'9' * 65};10;0\n".encode())
    assert too_long.json()["invalid"] == 1
    # Кириллическая «О» визуально не отличается от латинской «O» — счёт-гомоглиф
    # молча стал бы вторым, «пустым» счётом.
    cyrillic = upload(client, "homoglyph.csv", "account_number;debt;prepayment\n00О1;10;0\n".encode())
    assert cyrillic.json()["invalid"] == 1


def test_row_and_column_limits(client):
    rows = "".join(f"{i:05d};0;10\n" for i in range(10001))
    assert upload(client, "many.csv", ("account_number;debt;prepayment\n" + rows).encode()).status_code == 422
    wide_header = ";".join(["account_number", "debt", "prepayment"] + [f"c{i}" for i in range(28)])
    wide = f"{wide_header}\n001;0;10{';x' * 28}\n"
    assert upload(client, "wide.csv", wide.encode()).status_code == 422


def test_history_and_payment_caps(client):
    for day in range(1, 52):
        activate(client, preview(client, f"account_number;debt;prepayment\n001;{day};0\n", as_of=f"2026-07-{day % 28 + 1:02d}"))
    assert len(balance(client)["history"]) == 50
    payments = "".join(f"001;op-{i};2026-09-01;10\n" for i in range(201))
    activate(client, upload(client, "pay.csv", ("account_number;operation_id;paid_at;amount\n" + payments).encode(), kind="payments"))
    assert len(balance(client)["payments"]) == 200


def test_payments_are_ordered_by_payment_date_not_batch_date(client):
    """Отсечение «последних 200» идёт по дате платежа: свежий платёж из старой
    выгрузки не должен оказаться ниже старого платежа из свежей выгрузки."""
    old_batch = upload(client, "old.csv", b"account_number;operation_id;paid_at;amount\n001;fresh;2026-09-05;10\n",
                       kind="payments", as_of="2026-08-01")
    new_batch = upload(client, "new.csv", b"account_number;operation_id;paid_at;amount\n001;stale;2026-08-01;20\n",
                       kind="payments", as_of="2026-09-01")
    activate(client, old_batch)
    activate(client, new_batch)
    assert [row["operation_id"] for row in balance(client)["payments"]] == ["fresh", "stale"]


def test_payments_batch_reactivation_recreates_claims(client):
    batch = upload(client, "pay.csv", b"account_number;operation_id;paid_at;amount\n001;op-1;2026-09-01;10\n", kind="payments")
    activate(client, batch)
    batch_id = batch.json()["id"]
    assert client.post(f"/v1/imports/{batch_id}/deactivate", json={"reason": "ошибочная выгрузка"}).status_code == 200
    assert balance(client)["payments"] == []
    assert client.post(f"/v1/imports/{batch_id}/activate").status_code == 200
    assert [row["operation_id"] for row in balance(client)["payments"]] == ["op-1"]


def test_deactivate_non_active_batch_conflicts(client):
    """Раньше деактивация preview-импорта отвечала 200 и молча ничего не делала."""
    report = preview(client, "account_number;debt;prepayment\n001;10;0\n")
    batch_id = report.json()["id"]
    assert client.post(f"/v1/imports/{batch_id}/deactivate", json={"reason": "ошибка"}).status_code == 409
    activate(client, report)
    assert client.post(f"/v1/imports/{batch_id}/deactivate", json={"reason": "ошибка"}).status_code == 200
    assert client.post(f"/v1/imports/{batch_id}/deactivate", json={"reason": "ошибка"}).status_code == 409
    assert [e["action"] for e in client.get(f"/v1/imports/{batch_id}").json()["audit"]] == ["preview", "activate", "deactivate"]


def test_short_service_token_fails_fast(tmp_path):
    with pytest.raises(RuntimeError):
        create_app(f"sqlite:///{tmp_path / 'short.db'}", "too-short", initialize=True)


def test_identifier_formula_prefixes_and_note_control_chars(client):
    formula = upload(client, "formula.csv", b"account_number;operation_id;paid_at;amount\n001;-1+1;2026-09-01;10\n", kind="payments")
    assert formula.json()["invalid"] == 1
    noted = upload(client, "note.csv", "account_number;debt;prepayment;note\n001;10;0;без\tсчётчика\n".encode())
    assert noted.json()["invalid"] == 0
    assert "\t" not in noted.json()["rows"][0]["note"]


def test_declared_zip_size_is_not_trusted(client):
    import zipfile
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("xl/worksheets/sheet1.xml", b"0" * (40 * 1024 * 1024))
    response = upload(client, "bomb.xlsx", stream.getvalue())
    assert response.status_code == 422
    assert "слишком большой" in response.json()["detail"]
