from tests.conftest import make_meter, make_object


def test_object_type_and_tag_crud(admin):
    resp = admin.post("/v1/object-types", json={"name": "Фонтан"})
    assert resp.status_code == 201
    type_id = resp.json()["data"]["id"]

    # duplicate name conflicts
    assert admin.post("/v1/object-types", json={"name": "Фонтан"}).status_code == 409

    resp = admin.patch(f"/v1/object-types/{type_id}", json={"name": "Фонтан большой"})
    assert resp.status_code == 200
    assert resp.json()["data"]["name"] == "Фонтан большой"

    resp = admin.post("/v1/tags", json={"name": "полив"})
    assert resp.status_code == 201


def test_object_tree_and_cycle_guard(admin):
    root = make_object(admin, "Территория")
    child = make_object(admin, "Двор 1", parent_id=root["id"])
    grandchild = make_object(admin, "Фонтан двора", parent_id=child["id"])

    # Moving root under its grandchild would create a cycle
    resp = admin.patch(f"/v1/objects/{root['id']}", json={"parent_id": grandchild["id"]})
    assert resp.status_code == 400
    assert "цикл" in resp.json()["error"]["message"].lower()

    # Legal move
    resp = admin.patch(f"/v1/objects/{grandchild['id']}", json={"parent_id": root["id"]})
    assert resp.status_code == 200


def test_object_archive_guards(admin):
    parent = make_object(admin, "Насосная-А")
    child = make_object(admin, "Насос-1", parent_id=parent["id"])

    # active child blocks archive
    assert admin.post(f"/v1/objects/{parent['id']}/archive").status_code == 409
    assert admin.post(f"/v1/objects/{child['id']}/archive").status_code == 200

    # active meter blocks archive
    obj = make_object(admin, "Щитовая-Б")
    make_meter(admin, "ARCH-01", obj["id"])
    resp = admin.post(f"/v1/objects/{obj['id']}/archive")
    assert resp.status_code == 409
    assert "счётчики" in resp.json()["error"]["message"].lower()


def test_object_search_and_filters(admin):
    make_object(admin, "Полив южный", code="POL-S")
    # NB: sqlite lower() is ASCII-only, so the test query matches case; PG handles Cyrillic case-folding
    resp = admin.get("/v1/objects", params={"q": "Полив юж"})
    assert resp.status_code == 200
    names = [o["name"] for o in resp.json()["data"]]
    assert "Полив южный" in names


def test_object_rbac(viewer):
    resp = viewer.post("/v1/objects", json={"name": "Не должно создаться"})
    assert resp.status_code == 403
    assert viewer.get("/v1/objects").status_code == 200
