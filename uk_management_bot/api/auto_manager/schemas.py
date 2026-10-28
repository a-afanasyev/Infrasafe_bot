"""Pydantic-схема конфига авто-менеджера (dashboard API).

Валидация ЦЕЛИКОМ делегирована `services.auto_manager.config.validate_config`
(единственный источник бизнес-правил: HH:MM формат, IANA-таймзона, диапазон
`max_requests_per_run`) — здесь только типы полей + мост-`model_validator`, а
не независимый набор `field_validator`, который со временем мог бы разойтись
с валидацией бота (`validate_config` вызывается и из бот-хендлеров/шедулера).

PUT-payload — как у `board_config.schemas.BoardConfigData`: требует ПОЛНЫЙ
конфиг (все поля обязательны, без Pydantic-дефолтов). Merge-с-`DEFAULT_CONFIG`
поведение `validate_config` относится к сырому dict-пути бота (шедулер/меню-
хендлер); API-путь всегда шлёт/получает уже полный конфиг — так же, как
board_config, где PUT ожидает целиком заполненную модель.

⚠️ `mode="ai"`: общий `validate_config` принимает его всегда, API — только
при `settings.AI_MANAGER_ENABLED` (деплой-флаг площадки, см. settings.py):
без флага GET/PUT показывали бы режим, который здесь не работает. Клиенту
доступность сообщается read-only полем `ai_available`; обратно присланное
значение игнорируется.
"""
from copy import deepcopy
from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator

from uk_management_bot.config.settings import settings
from uk_management_bot.services.auto_manager.config import DEFAULT_CONFIG, validate_config


class SlaHours(BaseModel):
    """Нормативы сроков аналитики, часы (диапазон проверяет `validate_config`)."""

    critical: int
    high: int
    medium: int
    low: int


class AutoManagerConfigData(BaseModel):
    enabled: bool
    mode: Literal["rule", "ai"]
    window_start: str
    window_end: str
    timezone: str
    max_requests_per_run: int
    # Дефолт — для клиентов, присланных до появления поля; дашборд шлёт
    # конфиг целиком поверх свежего GET и поле не теряет.
    sla_hours: SlaHours = Field(
        default_factory=lambda: SlaHours(**DEFAULT_CONFIG["sla_hours"])
    )
    # Блок ИИ-режима: явное поле обязательно — у модели `extra="ignore"`, и без
    # него каждый PUT полного конфига с дашборда сбрасывал бы `ai` в дефолт.
    # Вложенная валидация — в `validate_config` (единый источник правил).
    ai: dict = Field(default_factory=lambda: deepcopy(DEFAULT_CONFIG["ai"]))
    sla: dict = Field(default_factory=lambda: deepcopy(DEFAULT_CONFIG["sla"]))
    # Read-only: доступен ли режим "ai" на площадке (деплой-флаг). Заполняет
    # роутер; присланное клиентом значение не учитывается.
    ai_available: Optional[bool] = None

    def config_dict(self) -> dict:
        """Конфиг для `save_config` — без read-only полей."""
        return self.model_dump(exclude={"ai_available"})

    @model_validator(mode="after")
    def _validate_via_shared_rules(self) -> "AutoManagerConfigData":
        """Прогоняет модель через общий `validate_config`.

        `validate_config` кидает `ValueError` на невалидном поле — Pydantic
        автоматически оборачивает `ValueError`, поднятый внутри валидатора,
        в свой `ValidationError` (см. docs: field/model validators).

        ⚠️ Цена шаринга: `loc` в 422-ответе для этих business-правил (HH:MM,
        таймзона, диапазон `max_requests_per_run`) указывает на `body`, а не
        на конкретное поле (в отличие от типовых/enum-нарушений — те ловит
        нативная Pydantic-валидация ДО этого метода и `loc` там уже
        field-specific). Имя поля всё равно есть в тексте `msg`. Осознанный
        компромисс: единый источник правды важнее точной адресации ошибки.
        """
        validate_config(self.config_dict())
        if self.mode == "ai" and not settings.AI_MANAGER_ENABLED:
            raise ValueError("mode: режим 'ai' недоступен на этой площадке (AI_MANAGER_ENABLED)")
        return self
