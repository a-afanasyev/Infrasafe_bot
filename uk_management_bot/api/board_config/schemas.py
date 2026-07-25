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

from pydantic import BaseModel, Field, field_validator

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
    limit: int = Field(6, ge=1, le=24)
    title: LocalizedText = Field(default_factory=LocalizedText)


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
    """


class BoardConfigUpdateIn(_BoardConfigFields):
    """Тело PUT /board-config. Без нормализации — мёрж и нормализация делаются
    сервис-слоем (`service.merge_and_save_board_config`)."""


# Alias для обратной совместимости: tests/api/test_board_config_layout_width.py
# (пиненный файл, не редактировать) импортирует `BoardConfigData` и полагается
# на нормализующее поведение — оно есть только у StoredBoardConfigData.
BoardConfigData = StoredBoardConfigData
