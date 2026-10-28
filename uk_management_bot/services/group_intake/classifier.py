"""LLM-классификатор Group Intake: «заявка ли это сообщение из ТГ-группы».

Вызов провайдера — общий клиент ``services/llm/client.py`` (structured
outputs, ретрай транзиентного сбоя, общий дедлайн, гейт ``retry_allowed``).
Правила модуля:
- вызывается СТРОГО из async-слоя, вне БД-транзакций;
- best-effort: любая ошибка (таймаут, refusal, max_tokens, битый JSON,
  недоступность API) — это PROCESSING_ERROR, а не «не заявка»: исходы
  различаются в логах/метриках. Реакция в группе — у вызывающего: без тега
  молчим (закреплённое сообщение группы объясняет «нет номера — нет заявки»),
  в тег-режиме автор получает просьбу повторить (BUG-192);
- телефоны в тексте маскируются до отправки провайдеру (``[PHONE]``,
  решение владельца 2026-09-23, A9-P3-5): адрес/квартира остаются — они
  нужны для извлечения ``address_hint``;
- ключ и тексты сообщений в логи не пишутся.
"""
import logging
import math
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from typing import Optional

from uk_management_bot.config.settings import settings
from uk_management_bot.services.llm.client import RetryGate, llm_json_async
from uk_management_bot.utils import pii

logger = logging.getLogger(__name__)

LOCATION_SCOPES = ("apartment", "building", "yard", "unknown")
ADDRESS_HINT_MAX_LEN = 100
_TEXT_LIMIT = 2000
_MAX_TOKENS = 300


class Outcome(str, Enum):
    """Исход классификации — «не заявка» и «сломалось» не смешиваются."""

    REQUEST = "request"
    NOT_REQUEST = "not_request"
    PROCESSING_ERROR = "processing_error"


@dataclass(frozen=True)
class ClassificationResult:
    outcome: Outcome
    category: Optional[str] = None        # канон-ключ или None
    urgency: Optional[str] = None         # low|medium|high|critical или None
    confidence: float = 0.0
    location_scope: str = "unknown"       # apartment|building|yard|unknown
    address_hint: Optional[str] = None    # упоминание адреса в тексте, ≤100
    # llm | keyword (переопределил other); хендлер добавляет default (фолбэк
    # тег-режима в other) и manual (правка в staff-приёмке)
    category_source: str = "llm"


_NOT_REQUEST = ClassificationResult(outcome=Outcome.NOT_REQUEST)
_ERROR = ClassificationResult(outcome=Outcome.PROCESSING_ERROR)

PHONE_PLACEHOLDER = "[PHONE]"


def mask_phones(text: str) -> str:
    """Заменить телефоны на ``[PHONE]`` перед отправкой текста внешнему LLM."""
    return pii.mask_phones(text, PHONE_PLACEHOLDER)


def _schema() -> dict:
    # SELECTABLE, не полный канон: служебную `engineering` (очередь InfraSafe)
    # модель выдавать не должна.
    from uk_management_bot.utils.categories import SELECTABLE_CATEGORY_KEYS
    from uk_management_bot.utils.constants import URGENCY_VALUES

    return {
        "type": "object",
        "properties": {
            "is_request": {"type": "boolean"},
            "category": {"type": "string", "enum": list(SELECTABLE_CATEGORY_KEYS)},
            "urgency": {"type": "string", "enum": list(URGENCY_VALUES)},
            "confidence": {"type": "number"},
            "location_scope": {"type": "string", "enum": list(LOCATION_SCOPES)},
            "address_hint": {"type": ["string", "null"]},
        },
        "required": [
            "is_request",
            "category",
            "urgency",
            "confidence",
            "location_scope",
            "address_hint",
        ],
        "additionalProperties": False,
    }


_BASE_PROMPT = (
    "Ты — диспетчер управляющей компании жилых домов. Тебе дают одно сообщение "
    "из общедомового Telegram-чата жителей (русский или узбекский язык, "
    "узбекский бывает и кириллицей, и латиницей, часто с сокращениями вроде "
    "«17 v» = дом 17). "
    "Определи, описывает ли оно КОНКРЕТНУЮ бытовую/коммунальную проблему, "
    "требующую реакции УК (заявку): поломка, протечка, отключение, мусор, "
    "лифт, канализация, полив и т.п. Болтовня, вопросы без проблемы, объявления, "
    "благодарности, политика — не заявка.\n"
    "category — тип проблемы, выбирай по глоссарию ниже; urgency — здравая "
    "оценка срочности (critical только при угрозе жизни/имуществу: пожар, "
    "потоп, газ); confidence — твоя уверенность 0..1, что это заявка; "
    "location_scope — где проблема: apartment (внутри квартиры автора), "
    "building (подъезд/лифт/крыша/подвал/стояк — общее в доме), "
    "yard (двор/улица/парковка/мусорка), unknown если непонятно; "
    "address_hint — точная подстрока сообщения с адресом (например «дом 12»), "
    "если автор его назвал, иначе null."
)

_GLOSSARY_RULES = (
    "Правила выбора category: other — только если ни одна категория не "
    "подходит. Полив, газон, клумбы, деревья, двор → landscaping. "
    "«elektrik», «svet», «chiroq» → electricity. «suv», «вода», подвал с водой "
    "→ plumbing."
)

_KEYWORD_HINT = "\n\n[подсказка по ключевым словам: предположительно {kw}; перепроверь по тексту]"


def _category_glossary() -> str:
    """Глоссарий категорий из канона: ключ (ru / uz): описание. Примеры: …"""
    from uk_management_bot.utils.categories import (
        SELECTABLE_CATEGORY_KEYS,
        get_category_display,
    )
    from uk_management_bot.services.group_intake.category_keywords import (
        CATEGORY_GLOSSARY,
    )

    lines = []
    for key in SELECTABLE_CATEGORY_KEYS:
        description, examples = CATEGORY_GLOSSARY[key]
        ru = get_category_display(key, "ru")
        uz = get_category_display(key, "uz")
        quoted = ", ".join(f"«{example}»" for example in examples)
        lines.append(f"- {key} ({ru} / {uz}): {description}. Примеры: {quoted}")  # html-raw: промпт LLM, не Telegram
    return "\n".join(lines)


@lru_cache(maxsize=1)
def _system_prompt() -> str:
    """Стабильный системный промпт (кэшируется и у нас, и у провайдера)."""
    return f"{_BASE_PROMPT}\n\nГлоссарий категорий:\n{_category_glossary()}\n\n{_GLOSSARY_RULES}"


def _parse_response(
    payload: dict, keyword_category: Optional[str] = None
) -> ClassificationResult:
    """Валидация ответа модели. Битые значения → PROCESSING_ERROR.

    `keyword_category` — хит детерминированного словаря по тексту: он
    переопределяет ТОЛЬКО вердикт `other` (у модели есть контекст: «нет
    горячей воды» → heating, а словарь сказал бы plumbing).
    """
    from uk_management_bot.utils.categories import (
        SELECTABLE_CATEGORY_KEYS,
        resolve_category_key,
    )
    from uk_management_bot.utils.constants import normalize_urgency

    try:
        is_request = bool(payload["is_request"])
        confidence = float(payload["confidence"])
        raw_category = str(payload["category"] or "").lower()
        raw_urgency = str(payload["urgency"] or "").lower()
        raw_scope = str(payload["location_scope"] or "").lower()
        raw_hint = payload.get("address_hint")
    except (KeyError, TypeError, ValueError):
        logger.warning("group_intake.processing_error: malformed classifier payload keys")
        return _ERROR

    if not (math.isfinite(confidence) and 0.0 <= confidence <= 1.0):
        logger.warning("group_intake.processing_error: confidence out of range")
        return _ERROR

    if not is_request or confidence < settings.GROUP_INTAKE_MIN_CONFIDENCE:
        return _NOT_REQUEST

    # resolve_category_key возвращает ОРИГИНАЛ для неизвестных значений —
    # ужесточаем: всё, что не SELECTABLE-ключ после резолва, становится "other".
    # Именно SELECTABLE, а не полный канон: служебная `engineering` (очередь
    # InfraSafe) в схеме модели отсутствует, и «протёкшее» значение не должно
    # становиться категорией заявки из группы (ревью 2026-09-03).
    category = resolve_category_key(raw_category)
    if category not in SELECTABLE_CATEGORY_KEYS:
        category = "other"
    category_source = "llm"
    if category == "other" and keyword_category:
        category = keyword_category
        category_source = "keyword"
    logger.info(
        "group_intake.category: llm=%s kw=%s final=%s source=%s",
        raw_category, keyword_category, category, category_source,
    )
    urgency = normalize_urgency(raw_urgency) or "low"
    scope = raw_scope if raw_scope in LOCATION_SCOPES else "unknown"
    hint = None
    if isinstance(raw_hint, str):
        hint = raw_hint.strip()[:ADDRESS_HINT_MAX_LEN] or None

    return ClassificationResult(
        outcome=Outcome.REQUEST,
        category=category,
        urgency=urgency,
        confidence=confidence,
        location_scope=scope,
        address_hint=hint,
        category_source=category_source,
    )


async def classify_message(
    text: str,
    *,
    retry_allowed: Optional[RetryGate] = None,
) -> ClassificationResult:
    """Классифицировать текст сообщения. Никогда не бросает исключений.

    ``retry_allowed`` — гейт повтора (лимитер группы у вызывающего): повтор —
    второй платный вызов и должен считаться наравне с первым.
    """
    from uk_management_bot.services.group_intake.category_keywords import guess_category

    # Подсказка — в user-сообщение, не в system: system стабилен и кэшируется.
    keyword_category = guess_category(text)
    # Маскирование ДО усечения: телефон на границе лимита иначе ушёл бы
    # хвостом, который шаблон уже не узнаёт.
    content = mask_phones(text)[:_TEXT_LIMIT]
    if keyword_category:
        content += _KEYWORD_HINT.format(kw=keyword_category)

    payload = await llm_json_async(
        system=_system_prompt(),
        user=content,
        schema=_schema(),
        model=settings.GROUP_INTAKE_MODEL,
        timeout=settings.GROUP_INTAKE_LLM_TIMEOUT,
        max_tokens=_MAX_TOKENS,
        retry_allowed=retry_allowed,
        tag="group_intake",
    )
    if payload is None:
        return _ERROR
    return _parse_response(payload, keyword_category=keyword_category)
