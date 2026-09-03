"""AUD5-APIFE-6: входные схемы не глотают неизвестные ключи молча.

Грабля стреляла дважды. Первый раз — `width` у layout-элемента: поле добавили
на фронте, в pydantic-схему внести забыли, PUT возвращал 200, а ширина не
сохранялась (память `project_board_layout_half_width`). Второй — при заведении
блока `work_reports`. Оба раза «успешный» ответ означал потерю данных, и оба
раза искали в UI.

Асимметрия рисков, из-за которой строгость ставится ТОЛЬКО на вход:

* вход — клиент прислал ключ, которого схема не знает: почти всегда опечатка
  или клиент новее бэкенда. Тихий дроп маскирует и то, и другое;
* чтение — строка в БД содержит ключ, которого схема не знает: это штатное
  состояние ОТКАТА (релиз добавил поле, образ вернули назад). `load_board_config`
  на ValidationError отдаёт `DEFAULT_BOARD_CONFIG` целиком, поэтому строгость там
  превратила бы один незнакомый ключ в обнуление всей публичной витрины — имя
  организации, контакты, телефон, объявления.

Отсюда две группы тестов: вход обязан отвечать 422, чтение обязано пережить
незнакомый ключ.
"""
import copy

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.api.board_config.defaults import DEFAULT_BOARD_CONFIG
from uk_management_bot.database.models.board_config import BoardConfig
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.user import User

BOARD_URL = "/api/v2/board-config"
PATCH_URL = "/api/v2/requests/{number}"


def _valid_body() -> dict:
    return copy.deepcopy(DEFAULT_BOARD_CONFIG)


@pytest_asyncio.fixture
async def applicant_user(db_session: AsyncSession):
    u = User(telegram_id=778101, username="appl", first_name="A", last_name="B",
             roles='["applicant"]', status="approved")
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    return u


# ── Вход: PUT /board-config ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_valid_body_still_saves(client):
    """Контрольный: строгость не должна ломать штатное тело."""
    assert (await client.put(BOARD_URL, json=_valid_body())).status_code == 200


@pytest.mark.asyncio
async def test_unknown_top_level_key_rejected(client):
    body = _valid_body()
    body["quick_links"] = [{"url": "https://example.com"}]

    r = await client.put(BOARD_URL, json=body)

    assert r.status_code == 422
    assert "quick_links" in str(r.json())


@pytest.mark.asyncio
async def test_typo_in_layout_item_rejected(client):
    """Исходный случай: `width` с опечаткой уезжал в никуда с ответом 200."""
    body = _valid_body()
    body["layout"][0] = {**body["layout"][0], "widht": "half"}

    r = await client.put(BOARD_URL, json=body)

    assert r.status_code == 422
    assert "widht" in str(r.json())


@pytest.mark.asyncio
async def test_unknown_key_inside_work_reports_rejected(client):
    body = _valid_body()
    body["work_reports"] = {**body.get("work_reports", {}), "moderation": False}

    r = await client.put(BOARD_URL, json=body)

    assert r.status_code == 422


@pytest.mark.asyncio
async def test_unknown_key_in_deeply_nested_model_rejected(client):
    """Строгость должна доставать до самого дна: `LocalizedText` — третий уровень."""
    body = _valid_body()
    body["org"]["name"] = {**body["org"]["name"], "en": "Management Co"}

    r = await client.put(BOARD_URL, json=body)

    assert r.status_code == 422


@pytest.mark.asyncio
async def test_unknown_key_in_announcement_rejected(client):
    body = _valid_body()
    body["announcements"][0] = {**body["announcements"][0], "pinned": True}

    assert (await client.put(BOARD_URL, json=body)).status_code == 422


# ── Чтение: строка в БД с чужим ключом переживается ──────────────────────


@pytest.mark.asyncio
async def test_stored_row_with_unknown_key_still_serves_real_config(
    client, db_session: AsyncSession, manager_user
):
    """Сценарий отката: в строке лежит поле от более новой версии кода.

    Витрина обязана продолжать показывать сохранённые данные, а не молча
    свалиться в дефолты — то есть модель ЧТЕНИЯ остаётся толерантной.
    """
    data = _valid_body()
    data["org"]["name"] = {"ru": "ТСЖ Тест", "uz": "Test"}
    data["future_module"] = {"whatever": 1}
    data["layout"][0] = {**data["layout"][0], "height": "tall"}
    db_session.add(BoardConfig(id=1, data=data, updated_by=manager_user.id))
    await db_session.commit()

    r = await client.get("/api/v2/public/board-config")

    assert r.status_code == 200
    assert r.json()["org"]["name"]["ru"] == "ТСЖ Тест"


# ── Вход: PATCH /api/v2/requests/{number} ────────────────────────────────


@pytest.mark.asyncio
async def test_unknown_key_in_request_patch_rejected(client, db_session, applicant_user):
    db_session.add(Request(request_number="260101-777", user_id=applicant_user.id,
                           category="electricity", description="d",
                           status="В работе", urgency="low"))
    await db_session.commit()

    r = await client.patch(PATCH_URL.format(number="260101-777"),
                           json={"status": "Выполнена", "completion_note": "готово"})

    assert r.status_code == 422
    assert "completion_note" in str(r.json())


@pytest.mark.parametrize("payload", [
    {"status": "Выполнена", "completion_report": "готово"},
    {"status": "В работе", "executor_id": 7},
    {"status": "В работе", "assign_to_duty": True},
    {"status": "Закуп", "requested_materials": "трубы"},
    {"status": "Уточнение", "notes": "адрес?"},
    {"status": "Исполнено", "manager_confirmed": True, "manager_confirmation_notes": "ок"},
    {"status": "Возвращена", "return_reason": "не доделано"},
    {"status": "Принято", "rating": 5},
    {"urgency": "high"},
])
def test_known_keys_in_request_patch_still_accepted(payload):
    """Все тела, которыми реально ходят дашборд и TWA, обязаны проходить схему.

    Проверяем саму схему, а не HTTP: через ручку сюда примешались бы отказы
    движка (недопустимый переход, чужой исполнитель) — а вопрос здесь ровно
    один, не сузилась ли схема. Список сверен с вызовами `apiClient.patch` /
    `twaClient.patch` во фронте; если ключ выпадет, тест покраснеет раньше,
    чем менеджер увидит 422 в браузере.
    """
    from uk_management_bot.api.requests.schemas import UpdateRequestBody

    assert UpdateRequestBody(**payload) is not None


def test_category_is_not_a_patch_key_and_change_body_forbids_extra():
    """Категория меняется своим эндпоинтом (PATCH …/category, канон
    MANAGER_CHANGE_CATEGORY); в теле общего PATCH это по-прежнему лишний ключ."""
    from pydantic import ValidationError

    from uk_management_bot.api.requests.schemas import ChangeCategoryBody, UpdateRequestBody

    with pytest.raises(ValidationError):
        UpdateRequestBody(category="plumbing")
    assert ChangeCategoryBody(category="Сантехника").category == "plumbing"
    with pytest.raises(ValidationError):
        ChangeCategoryBody(category="plumbing", urgency="high")


# ── Вход: PUT /api/v2/work-reports/settings ──────────────────────────────


@pytest.mark.asyncio
async def test_unknown_key_in_work_reports_settings_rejected(client, monkeypatch):
    """Тот же singleton board_config, вторая дверь в него — правило одно."""
    from uk_management_bot.config.settings import settings
    monkeypatch.setattr(settings, "WORK_REPORTS_ENABLED", True)

    r = await client.put("/api/v2/work-reports/settings",
                         json={"autopost": True, "moderation_required": False})

    assert r.status_code == 422
