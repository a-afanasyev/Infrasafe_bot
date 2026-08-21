"""LLM-классификатор Group Intake: «заявка ли это сообщение из ТГ-группы».

Anthropic API, structured outputs (output_config.format c json_schema).
Правила модуля:
- вызывается СТРОГО из async-слоя, вне БД-транзакций;
- best-effort: любая ошибка (таймаут, refusal, max_tokens, битый JSON,
  недоступность API) — это PROCESSING_ERROR, а не «не заявка»: исходы
  различаются в логах/метриках, но в группе одинаково молчим (закреплённое
  сообщение группы объясняет «нет номера — нет заявки»);
- ключ и тексты сообщений в логи не пишутся.
"""
import asyncio
import logging
import math
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from uk_management_bot.config.settings import settings

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


_NOT_REQUEST = ClassificationResult(outcome=Outcome.NOT_REQUEST)
_ERROR = ClassificationResult(outcome=Outcome.PROCESSING_ERROR)

# Ленивая инициализация: модуль импортируется и в окружениях без ключа
# (тесты, выключенный флаг) — клиент создаётся при первом вызове.
_client = None


def _get_client():
    global _client
    if _client is None:
        from anthropic import AsyncAnthropic

        _client = AsyncAnthropic(
            api_key=settings.ANTHROPIC_API_KEY,
            timeout=settings.GROUP_INTAKE_LLM_TIMEOUT,
            max_retries=0,
        )
    return _client


def _schema() -> dict:
    from uk_management_bot.keyboards.requests import CANONICAL_CATEGORY_KEYS
    from uk_management_bot.utils.constants import URGENCY_VALUES

    return {
        "type": "object",
        "properties": {
            "is_request": {"type": "boolean"},
            "category": {"type": "string", "enum": list(CANONICAL_CATEGORY_KEYS)},
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


_SYSTEM_PROMPT = (
    "Ты — диспетчер управляющей компании жилых домов. Тебе дают одно сообщение "
    "из общедомового Telegram-чата жителей (русский или узбекский язык). "
    "Определи, описывает ли оно КОНКРЕТНУЮ бытовую/коммунальную проблему, "
    "требующую реакции УК (заявку): поломка, протечка, отключение, мусор, "
    "лифт, канализация и т.п. Болтовня, вопросы без проблемы, объявления, "
    "благодарности, политика — не заявка.\n"
    "category — тип проблемы; urgency — здравая оценка срочности "
    "(critical только при угрозе жизни/имуществу: пожар, потоп, газ); "
    "confidence — твоя уверенность 0..1, что это заявка; "
    "location_scope — где проблема: apartment (внутри квартиры автора), "
    "building (подъезд/лифт/крыша/подвал/стояк — общее в доме), "
    "yard (двор/улица/парковка/мусорка), unknown если непонятно; "
    "address_hint — точная подстрока сообщения с адресом (например «дом 12»), "
    "если автор его назвал, иначе null."
)


def _parse_response(payload: dict) -> ClassificationResult:
    """Валидация ответа модели. Битые значения → PROCESSING_ERROR."""
    from uk_management_bot.keyboards.requests import (
        CANONICAL_CATEGORY_KEYS,
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
    # ужесточаем: всё, что не канон-ключ после резолва, становится "other".
    category = resolve_category_key(raw_category)
    if category not in CANONICAL_CATEGORY_KEYS:
        category = "other"
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
    )


async def classify_message(text: str) -> ClassificationResult:
    """Классифицировать текст сообщения. Никогда не бросает исключений."""
    import json

    try:
        async with asyncio.timeout(settings.GROUP_INTAKE_LLM_TIMEOUT):
            response = await _get_client().messages.create(
                model=settings.GROUP_INTAKE_MODEL,
                max_tokens=_MAX_TOKENS,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": text[:_TEXT_LIMIT]}],
                output_config={"format": {"type": "json_schema", "schema": _schema()}},
            )
    except Exception as e:  # таймаут, сеть, 4xx/5xx, что угодно — best-effort
        logger.warning("group_intake.processing_error: llm call failed: %s", type(e).__name__)
        return _ERROR

    if getattr(response, "stop_reason", None) in ("refusal", "max_tokens"):
        logger.warning(
            "group_intake.processing_error: stop_reason=%s", response.stop_reason
        )
        return _ERROR

    blocks = getattr(response, "content", None) or []
    text_block = next((b for b in blocks if getattr(b, "type", "") == "text"), None)
    if text_block is None or not getattr(text_block, "text", ""):
        logger.warning("group_intake.processing_error: empty content")
        return _ERROR

    try:
        payload = json.loads(text_block.text)
    except (json.JSONDecodeError, TypeError):
        logger.warning("group_intake.processing_error: invalid json")
        return _ERROR

    return _parse_response(payload)
