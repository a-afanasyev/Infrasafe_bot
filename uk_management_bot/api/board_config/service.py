"""Общий сервис-слой конфига публичной витрины resident-board.

Держит логику загрузки board_config и форматирования часов работы, чтобы её
переиспользовали и `board_config/router.py` (публичное табло), и
`routes/announcements.py` (главная TWA). Стиль — как api/*/service.py (ARC-06).

⚠️ `CONFIG_ROW_ID` живёт здесь, а не в router.py: router.py импортит из этого
модуля, поэтому обратный импорт создал бы цикл.
"""
import copy
import logging
from datetime import datetime, timezone

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.api.board_config.defaults import DEFAULT_BOARD_CONFIG, enabled_module_ids
from uk_management_bot.api.board_config.schemas import (
    BoardConfigResponse,
    StoredBoardConfigData,
    WorkingHourCfg,
)
from uk_management_bot.database.models.board_config import BoardConfig

logger = logging.getLogger(__name__)

CONFIG_ROW_ID = 1

# Порядок дней недели (схема валидирует состав 7 дней, но не порядок).
_DAY_ORDER = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")

# Короткие названия дней и метка выходного. SSOT для TWA-ответа — здесь (бэк
# сам склеивает строку часов). Держать в соответствии с frontend i18n-ключами
# days.short.* и board.editor.closed (ru.json), чтобы TWA и веб-табло совпадали.
DAY_SHORT = {
    "ru": {"mon": "Пн", "tue": "Вт", "wed": "Ср", "thu": "Чт", "fri": "Пт", "sat": "Сб", "sun": "Вс"},
    "uz": {"mon": "Du", "tue": "Se", "wed": "Ch", "thu": "Pa", "fri": "Ju", "sat": "Sh", "sun": "Ya"},
}
CLOSED_LABEL = {"ru": "Выходной", "uz": "Dam olish kuni"}


async def load_board_config(db: AsyncSession) -> StoredBoardConfigData:
    """Загрузить строку board_config (id=1) или отдать дефолт.

    Fallback на `DEFAULT_BOARD_CONFIG`, если строки ещё нет (миграция не
    накатана) — публичные потребители не должны падать/белеть.
    """
    data = DEFAULT_BOARD_CONFIG
    try:
        result = await db.execute(select(BoardConfig).where(BoardConfig.id == CONFIG_ROW_ID))
        row = result.scalar_one_or_none()
        if row is not None and row.data:
            data = row.data
    except (OperationalError, ProgrammingError) as e:
        logger.warning("board_config недоступен, отдаю дефолт: %s", e)

    try:
        return StoredBoardConfigData.model_validate(data)
    except ValidationError as e:
        # Битая/легаси-строка в БД (ручная правка, эволюция схемы без бэкфилла)
        # не должна ронять публичные эндпоинты 500 — падаем в дефолт.
        logger.warning("board_config.data не проходит схему, отдаю дефолт: %s", e)
        return StoredBoardConfigData.model_validate(DEFAULT_BOARD_CONFIG)


async def merge_and_save_board_config(
    db: AsyncSession,
    updates: dict,
    updated_by: int,
) -> StoredBoardConfigData:
    """Смёржить `updates` в сохранённый board_config и сохранить результат.

    Единая точка записи — сюда идёт и PUT редактора витрины, и (в будущей
    задаче) PUT настроек work-reports. `updates` — плоский dict, содержащий
    ТОЛЬКО те top-level ключи, которые вызывающий явно хочет перезаписать
    (см. router.py: `payload.model_dump(include=payload.model_fields_set)`).

    `layout` — единственное поле с union-мёржем, а не overwrite: это и есть
    фикс бага «старый клиент PUT'ом стирает модуль, включённый менеджером
    позже» — берём порядок из входящего списка (drag-and-drop клиента), затем
    дописываем те id из сохранённого layout, которых нет во входящем — не
    только "workreports", а любой id, отсутствующий в теле запроса.

    `work_reports.autopost_since` — серверное поле, клиентское значение
    игнорируется всегда: стамп на переходе False→True, сохранённое значение
    при True→True, None при *→False.
    """
    result = await db.execute(
        select(BoardConfig).where(BoardConfig.id == CONFIG_ROW_ID).with_for_update()
    )
    row = result.scalar_one_or_none()
    if row is not None and row.data:
        stored: dict = copy.deepcopy(row.data)
    else:
        stored = copy.deepcopy(DEFAULT_BOARD_CONFIG)

    # Deep copy (not a shallow `dict(stored)`): fields not touched by `updates`
    # (e.g. work_reports on a body that omits it) must not alias `stored`'s
    # nested dicts — the autopost_since stamping below mutates in place.
    merged = copy.deepcopy(stored)
    for key, value in updates.items():
        if key == "layout":
            continue
        merged[key] = value

    if "layout" in updates:
        incoming = updates["layout"] or []
        incoming_ids = {item["id"] for item in incoming}
        carried_over = [item for item in stored.get("layout", []) if item["id"] not in incoming_ids]
        merged["layout"] = list(incoming) + carried_over

    if "work_reports" in merged:
        before_autopost = bool(stored.get("work_reports", {}).get("autopost"))
        after_autopost = bool(merged["work_reports"].get("autopost"))
        if not before_autopost and after_autopost:
            merged["work_reports"]["autopost_since"] = datetime.now(timezone.utc).isoformat()
        elif after_autopost:
            merged["work_reports"]["autopost_since"] = stored.get("work_reports", {}).get(
                "autopost_since"
            )
        else:
            merged["work_reports"]["autopost_since"] = None

    normalized = StoredBoardConfigData.model_validate(merged)

    if row is None:
        db.add(
            BoardConfig(
                id=CONFIG_ROW_ID,
                data=normalized.model_dump(mode="json"),
                updated_by=updated_by,
            )
        )
    else:
        row.data = normalized.model_dump(mode="json")
        row.updated_by = updated_by
    await db.commit()

    return normalized


def to_public_response(cfg: StoredBoardConfigData) -> BoardConfigResponse:
    """Гейт по фиче-флагу на границе ответа: вырезать невключённые модули из layout.

    Возвращает НЕ-нормализующую модель (`BoardConfigResponse`), поэтому вырезанный
    "workreports" остаётся вырезанным и после повторной валидации через
    `response_model` — в отличие от StoredBoardConfigData, которая бы тут же
    зафиллила его обратно.
    """
    enabled = set(enabled_module_ids())
    data = cfg.model_dump(mode="json")
    data["layout"] = [item for item in data["layout"] if item["id"] in enabled]
    return BoardConfigResponse.model_validate(data)


def _day_display(hour: WorkingHourCfg, lang: str) -> str:
    """Отображаемое значение одного дня.

    closed=True → «Выходной»; иначе непустые open И close → «HH:MM–HH:MM»;
    иначе (неполное время) → «—».
    """
    if hour.closed:
        return CLOSED_LABEL[lang]
    open_ = hour.open.strip()
    close = hour.close.strip()
    if open_ and close:
        return f"{open_}–{close}"
    return "—"


def format_working_hours(hours: list[WorkingHourCfg], lang: str) -> str:
    """Многострочная сводка часов работы, группируя подряд идущие одинаковые дни.

    Напр. «Пн–Пт: 08:00–20:00\\nСб: 09:00–17:00\\nВс: Выходной».
    """
    by_day = {h.day: h for h in hours}
    # Упорядочить mon..sun (вход может быть в любом порядке — см. schemas.py).
    ordered = [by_day[d] for d in _DAY_ORDER if d in by_day]

    lines: list[str] = []
    i = 0
    n = len(ordered)
    while i < n:
        value = _day_display(ordered[i], lang)
        j = i
        while j + 1 < n and _day_display(ordered[j + 1], lang) == value:
            j += 1
        start = DAY_SHORT[lang][ordered[i].day]
        if j > i:
            end = DAY_SHORT[lang][ordered[j].day]
            lines.append(f"{start}–{end}: {value}")
        else:
            lines.append(f"{start}: {value}")
        i = j + 1

    return "\n".join(lines)
