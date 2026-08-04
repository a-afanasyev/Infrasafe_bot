"""Pydantic-схемы конфига публичной витрины resident-board.

Три отдельные модели вместо одной (было `BoardConfigData` и для хранения, и
для PUT/GET) — намеренно:

- `StoredBoardConfigData` — то, что лежит в БД / выходит из `load_board_config`.
  Единственная модель с нормализацией `layout` (см. `_normalize_layout`).
- `BoardConfigResponse` — `response_model` и GET, и PUT. БЕЗ нормализации:
  если сервис-слой уже отфильтровал выключенный модуль из словаря перед
  `response_model.model_validate(...)`, нормализующая модель бы тут же
  зафиллила его обратно ("модуля нет" == "надо подставить дефолт" с точки
  зрения нормализатора) — и серверный гейт по фиче-флагу сам себя бы обнулил
  на границе FastAPI-ответа. `BoardConfigResponse` не нормализует, поэтому
  фильтрация остаётся в силе.
- `BoardConfigUpdateIn` — тело PUT. Тоже без нормализации: сервис-слой мёржит
  его с сохранённым состоянием и только потом валидирует результат через
  `StoredBoardConfigData`.
"""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from uk_management_bot.api.board_config.defaults import ALL_MODULE_IDS, MODULE_DEFAULTS

_DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


class LocalizedText(BaseModel):
    ru: str = ""
    uz: str = ""


class OrgCfg(BaseModel):
    name: LocalizedText
    subtitle: LocalizedText


class ContactsCfg(BaseModel):
    dispatch_phone: str = ""
    dispatch_label: LocalizedText
    emergency: LocalizedText


class BotCfg(BaseModel):
    username: str = ""
    label: LocalizedText


class AnnouncementCfg(BaseModel):
    id: str
    icon: str = ""
    important: bool = False
    title: LocalizedText
    text: LocalizedText
    published_at: str = ""


class WorkingHourCfg(BaseModel):
    day: str
    open: str = ""
    close: str = ""
    closed: bool = False

    @field_validator("day")
    @classmethod
    def _known_day(cls, v: str) -> str:
        if v not in _DAYS:
            raise ValueError(f"day must be one of {_DAYS}")
        return v


class LayoutItem(BaseModel):
    id: str
    visible: bool = True
    # Ширина блока на табло: 'full' — на всю ширину; 'half' — половина. Два
    # соседних видимых 'half' встают в один ряд (см. ResidentBoardPage). Дефолт
    # 'full' → старые строки без поля остаются как раньше.
    width: Literal["full", "half"] = "full"

    # Без валидатора на `id`: неизвестные/битые id теперь допустимы на этом
    # уровне — фильтрация мусора и известных-но-выключенных модулей происходит
    # только в StoredBoardConfigData._normalize_layout / service.to_public_response.


class WorkReportsCfg(BaseModel):
    autopost: bool = False
    autopost_since: datetime | None = None
    # Публиковать БЕЗ модерации: черновик, у которого нашлись обе стороны фото,
    # уезжает в публичную ленту сразу, без подтверждения человеком. Единственный
    # контроль за СОДЕРЖИМЫМ снимка (номер двери, табличка с фамилией, госномер,
    # лицо) — это глаза модератора; адрес анонимизируется кодом, фото — нет.
    # Поэтому дефолт False, и в аудите такие публикации помечаются отдельным
    # действием `work_report.autopublish` с user_id=NULL, чтобы по журналу было
    # видно: человек это не подтверждал.
    autopublish: bool = False
    # Фильтр «какие категории вообще попадают в ленту». ПУСТОЙ СПИСОК = без
    # ограничения (все категории), а не «ни одной» — это фильтр, и пустой фильтр
    # ничего не отсекает. Существующие конфиги без этого поля поэтому продолжают
    # работать как раньше.
    categories: list[str] = Field(default_factory=list)
    limit: int = Field(6, ge=1, le=24)
    title: LocalizedText = Field(default_factory=LocalizedText)

    @field_validator("categories")
    @classmethod
    def _known_categories(cls, v: list[str]) -> list[str]:
        """Только канонические ключи категорий, без дублей, порядок сохраняем.

        Импорт ленивый — `keyboards.requests` тянет aiogram.types (тот же приём,
        что в api/work_reports/schemas.py и work_report_service).
        """
        from uk_management_bot.keyboards.requests import CANONICAL_CATEGORY_KEYS

        unknown = [c for c in v if c not in CANONICAL_CATEGORY_KEYS]
        if unknown:
            raise ValueError(
                f"unknown category keys: {unknown}; allowed: {sorted(CANONICAL_CATEGORY_KEYS)}"
            )
        seen: set[str] = set()
        deduped = []
        for c in v:
            if c not in seen:
                seen.add(c)
                deduped.append(c)
        return deduped


class _BoardConfigFields(BaseModel):
    """Общие поля конфига витрины. Не используется как самостоятельная API-модель
    (см. `StoredBoardConfigData` / `BoardConfigResponse` / `BoardConfigUpdateIn`)."""

    org: OrgCfg
    contacts: ContactsCfg
    bot: BotCfg
    announcements: list[AnnouncementCfg]
    working_hours: list[WorkingHourCfg]
    layout: list[LayoutItem]
    work_reports: WorkReportsCfg = Field(default_factory=WorkReportsCfg)

    @field_validator("working_hours")
    @classmethod
    def _seven_unique_days(cls, v: list[WorkingHourCfg]) -> list[WorkingHourCfg]:
        days = [w.day for w in v]
        if set(days) != set(_DAYS):
            raise ValueError("working_hours must cover exactly the 7 days mon..sun")
        return v


class StoredBoardConfigData(_BoardConfigFields):
    """То, что лежит в БД (и что отдаёт `load_board_config`).

    Единственная из трёх моделей, что нормализует `layout`.
    """

    @field_validator("layout")
    @classmethod
    def _normalize_layout(cls, v: list[LayoutItem]) -> list[LayoutItem]:
        """Привести layout к «все известные модули ровно один раз».

        Почему так, а не строгая валидация (как раньше `_all_modules_once`):
        появление нового модуля (напр. "workreports") не должно ронять старые
        PUT-тела с 5 элементами — их нужно молча дополнять, а не отклонять.

        Контракт:
        - Порядок выживших элементов НЕ меняется — layout перетаскиваемый
          (см. комментарий в defaults.py), и порядок, выбранный менеджером
          для уже известных ему модулей, должен сохраняться. Новые модули
          только ДОПИСЫВАЮТСЯ в конец, в порядке ALL_MODULE_IDS.
        - Неизвестные id (не входящие в ALL_MODULE_IDS) отбрасываются молча.
        - Дубликаты id схлопываются — побеждает первое вхождение.
        - Бэкфилл — по ALL_MODULE_IDS (а не enabled_module_ids()): хранимая
          строка должна содержать все известные модули независимо от
          settings.WORK_REPORTS_ENABLED — видимость снаружи фильтруется
          отдельно, на границе ответа (service.to_public_response), не здесь.
        - Идемпотентно: повторный прогон уже нормализованного списка через
          эту же валидацию не меняет результат.
        """
        seen: set[str] = set()
        kept: list[LayoutItem] = []
        for item in v:
            if item.id not in ALL_MODULE_IDS or item.id in seen:
                continue
            seen.add(item.id)
            kept.append(item)

        for module_id in ALL_MODULE_IDS:
            if module_id not in seen:
                kept.append(LayoutItem.model_validate(MODULE_DEFAULTS[module_id]))

        return kept


class BoardConfigResponse(_BoardConfigFields):
    """`response_model` для GET /public/board-config и PUT /board-config.

    Без нормализации: layout принимается/отдаётся ровно таким, каким его
    построил сервис-слой (к этому моменту уже отфильтрованным по фиче-флагу).

    `display_tz` (ARCH-137 B5) — зона показа развёртывания. Поле живёт ТОЛЬКО
    в ответе и заполняется в `to_public_response` (модель обслуживает и GET, и
    PUT — заполнение в хендлере уронило бы половину путей). В `BoardConfigUpdateIn`
    его НЕТ намеренно: вход строгий (`_StrictIn`), echo поля в PUT = 422 —
    фронт обязан отделять редактируемый конфиг от ответа.
    """

    display_tz: str


class _StrictIn(BaseModel):
    """Примесь для моделей ВХОДА: неизвестный ключ — 422, а не тихая потеря.

    Зачем строгость только на входе (AUD5-APIFE-6). Неизвестный ключ значит
    разное с разных сторон:

    - в теле запроса это почти всегда опечатка или клиент новее бэкенда; ответ
      200 с молча выброшенным полем читается вызывающим как «сохранено».
      Грабля уже стреляла дважды — `width` у layout-элемента и блок
      `work_reports`, оба раза искали в UI;
    - в строке БД это штатное состояние ОТКАТА: релиз добавил поле, образ
      вернули назад. `load_board_config` на ValidationError отдаёт
      `DEFAULT_BOARD_CONFIG` целиком, поэтому строгость на чтении превратила бы
      один незнакомый ключ в обнуление всей витрины — название организации,
      контакты, телефон, объявления.

    Поэтому строгие варианты вложенных моделей отдельные, а `StoredBoardConfigData`
    и `BoardConfigResponse` продолжают использовать толерантные.
    """

    model_config = ConfigDict(extra="forbid")


class LocalizedTextIn(LocalizedText, _StrictIn):
    pass


class OrgCfgIn(OrgCfg, _StrictIn):
    name: LocalizedTextIn
    subtitle: LocalizedTextIn


class ContactsCfgIn(ContactsCfg, _StrictIn):
    dispatch_label: LocalizedTextIn
    emergency: LocalizedTextIn


class BotCfgIn(BotCfg, _StrictIn):
    label: LocalizedTextIn


class AnnouncementCfgIn(AnnouncementCfg, _StrictIn):
    title: LocalizedTextIn
    text: LocalizedTextIn


class WorkingHourCfgIn(WorkingHourCfg, _StrictIn):
    pass


class LayoutItemIn(LayoutItem, _StrictIn):
    pass


class WorkReportsCfgIn(WorkReportsCfg, _StrictIn):
    title: LocalizedTextIn = Field(default_factory=LocalizedTextIn)


class BoardConfigUpdateIn(_BoardConfigFields, _StrictIn):
    """Тело PUT /board-config. Без нормализации — мёрж и нормализация делаются
    сервис-слоем (`service.merge_and_save_board_config`).

    Поля переобъявлены строгими вариантами: `extra="forbid"` действует только на
    той модели, где объявлен, а терялись как раз вложенные поля (`width` внутри
    layout-элемента), не top-level.
    """

    org: OrgCfgIn
    contacts: ContactsCfgIn
    bot: BotCfgIn
    announcements: list[AnnouncementCfgIn]
    working_hours: list[WorkingHourCfgIn]
    layout: list[LayoutItemIn]
    work_reports: WorkReportsCfgIn = Field(default_factory=WorkReportsCfgIn)


# Alias для обратной совместимости: tests/api/test_board_config_layout_width.py
# (пиненный файл, не редактировать) импортирует `BoardConfigData` и полагается
# на нормализующее поведение — оно есть только у StoredBoardConfigData.
BoardConfigData = StoredBoardConfigData
