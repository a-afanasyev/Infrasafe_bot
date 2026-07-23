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

⚠️ `mode`: API-схема ЖЁСТЧЕ общего `validate_config` (который принимает и
"rule", и "ai" — так исторически решили для forward-compat с Phase 2). Здесь
`Literal["rule"]` намеренно ýже: до появления реального ИИ-движка (Phase 2,
`services/auto_manager/ai_engine.py`, требует ANTHROPIC_API_KEY) оркестратор
всё равно ИГНОРИРУЕТ `mode` и всегда работает по правилу — разрешать API
сохранять "ai" уже сейчас означало бы, что GET/PUT показывают режим, который
фактически не работает (ни бот, ни дашборд и так не могут выбрать "ai" —
обе UI кнопки заблокированы/no-op). Разрешить "ai" здесь тоже нужно будет
РОВНО когда Phase 2 реально подключит движок к оркестратору, не раньше.
"""
from typing import Literal

from pydantic import BaseModel, model_validator

from uk_management_bot.services.auto_manager.config import validate_config


class AutoManagerConfigData(BaseModel):
    enabled: bool
    mode: Literal["rule"]
    window_start: str
    window_end: str
    timezone: str
    max_requests_per_run: int

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
        validate_config(self.model_dump())
        return self
