"""Сервис паспорта дома: правка под версией, «нет данных», статусы, редакции, общие объекты (sqlite)."""
from datetime import date

import pytest
from sqlalchemy import select

from uk_management_bot.database.models.building_passport import BuildingPassportEvent, BuildingPassportRevision
from uk_management_bot.services.building_passport import schema, validation
from uk_management_bot.services.building_passport import service as svc
from uk_management_bot.services.building_passport.service import Actor, PassportError

ENGINEER = Actor(11, "Инженер Иванов")
MANAGER = Actor(1, "Менеджер Петров")


@pytest.fixture
async def db(el_async_factory, el_seed):
    async with el_async_factory() as session:
        session.add_all([
            el_seed.yard(), el_seed.building(1), el_seed.building(2, address="д. 7"),
            el_seed.building(3, address="д. 9", is_active=False),
            el_seed.user(1, roles='["manager"]'), el_seed.user(11, roles='["executor","engineer"]'),
        ])
        await session.commit()
        yield session


async def _patch(db, building_id=1, actor=ENGINEER, **kw):
    current = await svc.view(db, building_id)
    kw.setdefault("expected_version", current["version"])
    return await svc.patch(db, building_id, actor, **kw)


async def _refused(coro) -> PassportError:
    with pytest.raises(PassportError) as exc:
        await coro
    return exc.value


async def _complete(db, building_id=1):
    """Довести паспорт до полного: всё неотвеченное закрывается как «нет данных»."""
    view = await _patch(db, building_id, meta={"inspection_date": "2026-11-20"})
    reasons = {key: "нет документов" for key in view["missing"] if key not in validation._groups()}
    absent = {key: True for key in view["missing"] if key in validation._groups()}
    return await _patch(db, building_id, unknown=reasons, absent=absent)


# ── чтение и правка ─────────────────────────────────────────────────────────

async def test_empty_passport_reads_as_not_started_without_writing(db):
    view = await svc.view(db, 1)
    assert (view["status"], view["version"], view["values"]) == ("not_started", 0, {})
    assert view["progress"]["done"] == 0 and view["progress"]["total"] > 100
    assert view["hints"]["floors"] == 9 and view["hints"]["entrances"] == 4


async def test_patch_saves_bumps_version_and_logs(db):
    view = await _patch(db, values={"floors": "9", "cadastre_no": "10:08:01"})
    assert view["version"] == 1 and view["values"]["floors"] == 9
    assert view["schema_version"] == schema.SCHEMA_VERSION
    event = (await db.execute(select(BuildingPassportEvent))).scalar_one()
    assert event.changes == {"floors": [None, 9], "cadastre_no": [None, "10:08:01"]}
    assert (event.actor_id, event.actor_name, event.kind) == (11, "Инженер Иванов", "values")


async def test_bad_value_is_refused_and_nothing_is_saved(db):
    error = await _refused(_patch(db, values={"floors": 9, "plot_area": -5}))
    assert (error.code, error.http_status, error.keys) == ("negative", 422, ("plot_area",))
    assert (await svc.view(db, 1))["version"] == 0


async def test_unchanged_value_does_not_create_a_version(db):
    await _patch(db, values={"floors": 9})
    view = await _patch(db, values={"floors": 9})
    assert view["version"] == 1


async def test_stale_write_to_the_same_field_is_a_conflict(db):
    await _patch(db, values={"floors": 9})                      # версия 1
    await _patch(db, values={"floors": 12})                     # версия 2: кто-то поправил
    error = await _refused(svc.patch(db, 1, ENGINEER, expected_version=1, values={"floors": 10}))
    assert (error.code, error.http_status, error.keys) == ("stale", 409, ("floors",))


async def test_parallel_edits_of_different_fields_both_pass(db):
    await _patch(db, values={"floors": 9})                      # версия 1
    await _patch(db, values={"cadastre_no": "10:08:01"})        # версия 2
    view = await svc.patch(db, 1, MANAGER, expected_version=1, values={"built_year": 2019})
    assert view["version"] == 3
    assert (view["values"]["floors"], view["values"]["cadastre_no"], view["values"]["built_year"]) == (
        9, "10:08:01", 2019)


async def test_computed_fields_are_returned_but_not_stored(db):
    view = await _patch(db, values={"windows": [{"type": "plastic", "count": 4, "width": 1, "height": 2}]})
    assert view["values"]["windows_total_count"] == 4 and view["values"]["windows"][0]["area"] == 8
    stored = (await svc.load(db, 1)).values
    assert "windows_total_count" not in stored and "area" not in stored["windows"][0]


async def test_unknown_needs_a_reason_and_counts_as_answered(db):
    error = await _refused(_patch(db, unknown={"cadastre_no": " "}))
    assert error.code == "reason_required"
    view = await _patch(db, unknown={"cadastre_no": "документы не найдены"})
    assert view["unknown"] == {"cadastre_no": "документы не найдены"} and "cadastre_no" not in view["missing"]
    view = await _patch(db, values={"cadastre_no": "10:08:01"})
    assert view["unknown"] == {}, "значение снимает отметку «нет данных»"


async def test_absent_group_counts_as_answered(db):
    view = await _patch(db, absent={"doors": True})
    assert view["absent"] == ["doors"] and "doors" not in view["missing"]
    view = await _patch(db, values={"doors": [{"type": "metal", "count": 2}]})
    assert view["absent"] == [], "строки снимают отметку «нет в доме»"


async def test_inactive_building_is_readable_but_not_editable(db):
    assert (await svc.view(db, 3))["editable"] is False
    assert (await _refused(svc.patch(db, 3, ENGINEER, expected_version=0, values={"floors": 9}))).code == (
        "building_inactive")
    assert (await _refused(svc.view(db, 99))).http_status == 404


# ── статусы и редакции ──────────────────────────────────────────────────────

async def test_filled_requires_complete_passport(db):
    view = await _patch(db, values={"floors": 9})
    error = await _refused(svc.set_status(db, 1, ENGINEER, status="filled", expected_version=view["version"]))
    assert error.code == "incomplete"
    view = await _complete(db)
    view = await svc.set_status(db, 1, ENGINEER, status="filled", expected_version=view["version"])
    assert view["status"] == "filled"


async def test_filled_is_blocked_by_a_failed_check(db):
    await _patch(db, values={"facade_ok_pct": 70, "facade_bad_pct": 20})
    view = await _complete(db)
    assert view["issues"] == [{"key": "facade_bad_pct", "code": "sum_100"}]
    error = await _refused(svc.set_status(db, 1, ENGINEER, status="filled", expected_version=view["version"]))
    assert error.code == "incomplete"


async def test_only_signer_signs_and_signed_passport_is_locked(db):
    view = await _complete(db)
    view = await svc.set_status(db, 1, ENGINEER, status="filled", expected_version=view["version"])
    error = await _refused(svc.set_status(db, 1, ENGINEER, status="signed", expected_version=view["version"]))
    assert (error.code, error.http_status) == ("sign_forbidden", 403)

    view = await svc.set_status(db, 1, MANAGER, status="signed", expected_version=view["version"], can_sign=True)
    assert (view["status"], view["revision_no"], view["editable"]) == ("signed", 1, False)
    assert (await _refused(_patch(db, values={"floors": 10}))).code == "signed"

    revision = (await db.execute(select(BuildingPassportRevision))).scalar_one()
    assert revision.schema == schema.public_schema() and revision.form == schema.etalon()
    assert revision.meta["inspection_date"] == "2026-11-20" and revision.meta["address"] == "ул. Мира, д. 5"
    assert (revision.signed_by, revision.signed_by_name) == (1, "Менеджер Петров")


async def test_status_change_requires_the_exact_version(db):
    view = await _complete(db)
    await _patch(db, values={"floors": 9})
    error = await _refused(svc.set_status(db, 1, ENGINEER, status="filled", expected_version=view["version"]))
    assert (error.code, error.http_status) == ("stale", 409)


async def test_return_to_work_needs_a_reason_and_keeps_the_revision(db):
    view = await _complete(db)
    view = await svc.set_status(db, 1, ENGINEER, status="filled", expected_version=view["version"])
    view = await svc.set_status(db, 1, MANAGER, status="signed", expected_version=view["version"], can_sign=True)
    error = await _refused(svc.set_status(
        db, 1, MANAGER, status="collecting", expected_version=view["version"], can_sign=True))
    assert error.code == "reason_required"

    view = await svc.set_status(db, 1, MANAGER, status="collecting", expected_version=view["version"],
                                can_sign=True, reason="уточнить площадь участка")
    assert view["status"] == "collecting" and view["editable"] is True
    view = await _patch(db, values={"floors": 12})
    view = await svc.set_status(db, 1, ENGINEER, status="filled", expected_version=view["version"])
    view = await svc.set_status(db, 1, MANAGER, status="signed", expected_version=view["version"], can_sign=True)

    first, second = [await svc.revision(db, 1, n) for n in (1, 2)]
    assert view["revision_no"] == 2
    assert "floors" not in first["values"] and second["values"]["floors"] == 12, "редакция №1 не изменилась"
    assert [r["revision_no"] for r in await svc.revisions(db, 1)] == [2, 1]


async def test_revision_survives_schema_and_form_change(db, monkeypatch):
    view = await _complete(db)
    view = await svc.set_status(db, 1, ENGINEER, status="filled", expected_version=view["version"])
    await svc.set_status(db, 1, MANAGER, status="signed", expected_version=view["version"], can_sign=True)
    before = await svc.revision(db, 1, 1)

    monkeypatch.setattr(schema, "public_schema", lambda: {"version": 2, "sections": []})
    monkeypatch.setattr(schema, "etalon", lambda: {"rows": []})
    after = await svc.revision(db, 1, 1)
    assert after == before and after["schema"]["version"] == 1 and len(after["form"]["rows"]) == 252


# ── объекты, общие на несколько домов ───────────────────────────────────────

async def test_shared_unit_is_read_from_the_primary_building(db):
    await _patch(db, 1, values={"plot_area": 500, "green_share": 20})
    view = await _patch(db, 2, shared_from={"plot": 1})
    assert view["shared_from"] == {"plot": 1}
    assert (view["values"]["plot_area"], view["values"]["green_share"]) == (500.0, 20.0)
    assert not {"plot_area", "green_share"} & set(view["missing"])
    assert (await _refused(_patch(db, 2, values={"plot_area": 480}))).code == "shared_readonly"

    await _patch(db, 1, values={"plot_area": 520})
    assert (await svc.view(db, 2))["values"]["plot_area"] == 520.0, "копии нет — значение одно"


async def test_shared_reference_rules(db):
    assert (await _refused(_patch(db, 2, shared_from={"plot": 2}))).code == "shared_self"
    assert (await _refused(_patch(db, 2, shared_from={"plot": 99}))).code == "shared_primary_not_found"
    assert (await _refused(_patch(db, 2, shared_from={"yard": 1}))).code == "unknown_field"
    await _patch(db, 1, values={"plot_area": 500})
    await _patch(db, 2, shared_from={"plot": 1})
    assert (await _refused(_patch(db, 1, shared_from={"plot": 2}))).code == "shared_chain"
    assert (await _refused(_patch(db, 1, values={"plot_area": None}))).code == "shared_referenced"


async def test_signing_copies_shared_value_and_later_edits_do_not_touch_it(db):
    await _patch(db, 1, values={"plot_area": 500, "green_share": 20})
    await _patch(db, 2, shared_from={"plot": 1})
    view = await _complete(db, 2)
    view = await svc.set_status(db, 2, ENGINEER, status="filled", expected_version=view["version"])
    await svc.set_status(db, 2, MANAGER, status="signed", expected_version=view["version"], can_sign=True)

    await _patch(db, 1, values={"plot_area": 520})
    revision = await svc.revision(db, 2, 1)
    assert revision["values"]["plot_area"] == 500.0 and revision["shared_from"] == {"plot": 1}


async def test_referencing_building_waits_for_the_primary_value(db):
    """Пока основной дом не заполнил общий объект, дом со ссылкой не «Заполнен»."""
    await _patch(db, 1, values={"plot_area": 500})          # доли озеленения у основного дома ещё нет
    view = await _patch(db, 2, shared_from={"plot": 1})
    assert "green_share" in view["missing"] and "plot_area" not in view["missing"]
    assert (await _refused(_patch(db, 2, unknown={"green_share": "нет"}))).code == "shared_readonly"


# ── обзор и журнал ──────────────────────────────────────────────────────────

async def test_overview_lists_active_buildings_with_progress(db):
    await _patch(db, 1, values={"floors": 9})
    rows = await svc.overview(db)
    assert [r["building_id"] for r in rows] == [1, 2], "деактивированный дом в списке не показывается"
    assert rows[0]["progress"]["done"] == 1 and rows[1]["status"] == "not_started"


async def test_history_is_newest_first(db):
    await _patch(db, values={"floors": 9})
    await _patch(db, meta={"inspection_date": date(2026, 11, 20).isoformat(), "note": "осмотр с инженером"})
    history = await svc.history(db, 1)
    assert [e["kind"] for e in history] == ["values", "values"]
    assert history[0]["changes"]["meta.note"] == [None, "осмотр с инженером"]
