"""Триаж новой заявки: два независимых анализатора текста.

* ``detect_emergency`` — детерминированный словарь аварийных слов (газ,
  затопление, застрявший лифт, искрение). Работает всегда, в том числе при
  отказе LLM: аварийная заявка не должна зависеть от доступности провайдера.
* ``llm_triage_sync`` — structured output через общий ``services/llm``:
  категория по глоссарию, срочность, нужен ли уточняющий вопрос (и сам
  вопрос на RU/UZ), дубль среди открытых заявок адреса. Любая ошибка или
  уверенность ниже порога → ``None`` (вызывающий идёт в rule-путь).

Итоговая срочность — максимум из текущей, аварийной и LLM: модель может
только поднять. Модуль чистый (без БД): контекст приносит ``apply.py``.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from functools import lru_cache
from typing import Mapping, Optional, Sequence

from uk_management_bot.config.settings import settings
from uk_management_bot.services.llm.client import llm_json_sync
from uk_management_bot.utils import pii
from uk_management_bot.utils.constants import URGENCY_DEFAULT, URGENCY_ORDER, normalize_urgency

logger = logging.getLogger(__name__)

_TEXT_LIMIT = 2000
_MAX_TOKENS = 400
_REASONING_LIMIT = 200
_QUESTION_LIMIT = 300
PHONE_PLACEHOLDER = "[PHONE]"

# Аварийные маркеры (ru/uz кириллица и латиница), подстроки в нижнем регистре.
# Пол срочности: совпадение → critical независимо от LLM.
EMERGENCY_KEYWORDS: tuple[str, ...] = (
    "запах газа", "утечка газа", "газ", "gaz",
    "затоп", "потоп", "suv bos", "suv toshdi",
    "лифт застрял", "застрял в лифте", "lift qolib", "liftda qolib",
    "искрит", "горит", "дым", "пожар", "yong'in", "yongin", "tutun", "uchqun",
)

#: Кандидат на дубль: (request_number, category, description).
OpenRequest = tuple[str, str, str]


@dataclass(frozen=True)
class LlmTriage:
    category: Optional[str]            # канон-ключ или None = не менять
    urgency: Optional[str]             # канон-ключ или None = не менять
    needs_clarification: bool
    clarification_question: Mapping[str, str]   # {ru, uz}; пусто если не нужен
    duplicate_of: Optional[str]        # request_number из кандидатов
    confidence: float
    reasoning: str


@dataclass(frozen=True)
class TriageHints:
    emergency: Optional[str]           # "critical" | None
    llm: Optional[LlmTriage]


def mask_phones(text: str) -> str:
    return pii.mask_phones(text, PHONE_PLACEHOLDER)


# ───────────── детерминированная часть ─────────────


def detect_emergency(text: Optional[str], extra: Sequence[str] = ()) -> Optional[str]:
    """``"critical"`` при аварийном маркере в тексте, иначе None. Чистая.
    Базовые ``EMERGENCY_KEYWORDS`` действуют всегда; ``extra`` — дополнительные
    слова со страницы «Правила ИИ» (``ai.extra_emergency_keywords``)."""
    if not text:
        return None
    lowered = text.lower()
    return "critical" if any(marker in lowered for marker in (*EMERGENCY_KEYWORDS, *extra)) else None


def final_urgency(current: Optional[str], hints: TriageHints) -> str:
    """Максимум по ``URGENCY_ORDER``; неизвестная текущая → дефолт."""
    candidates = [normalize_urgency(current) or URGENCY_DEFAULT, hints.emergency]
    if hints.llm is not None:
        candidates.append(hints.llm.urgency)
    known = [u for u in candidates if u in URGENCY_ORDER]
    return max(known, key=URGENCY_ORDER.__getitem__)


# ───────────── LLM-часть ─────────────


def _schema() -> dict:
    # Плоская схема без minimum/maximum/maxLength/enum: structured outputs
    # такие ограничения поддерживают не полностью — словари и диапазоны
    # проверяет parse_llm_triage.
    return {
        "type": "object",
        "properties": {
            "category": {"type": "string"},
            "urgency": {"type": "string"},
            "needs_clarification": {"type": "boolean"},
            "clarification_question_ru": {"type": "string"},
            "clarification_question_uz": {"type": "string"},
            "duplicate_of": {"type": ["string", "null"]},
            "confidence": {"type": "number"},
            "reasoning": {"type": "string"},
        },
        "required": [
            "category", "urgency", "needs_clarification", "clarification_question_ru",
            "clarification_question_uz", "duplicate_of", "confidence", "reasoning",
        ],
        "additionalProperties": False,
    }


_BASE_PROMPT = (
    "Ты — диспетчер управляющей компании жилого комплекса. Тебе дают текст "
    "новой заявки жителя (русский или узбекский язык, узбекский бывает и "
    "кириллицей, и латиницей), категорию, которую выбрал житель, его язык и "
    "список открытых заявок по тому же адресу.\n"
    "Верни JSON:\n"
    "- category — ключ из глоссария ниже, который лучше всего описывает "
    "проблему (если выбранная жителем категория верна — повтори её; other — "
    "только если ничего не подходит);\n"
    "- urgency — low|medium|high|critical; critical только при угрозе жизни "
    "или имуществу (газ, потоп, пожар, застрявший человек);\n"
    "- needs_clarification — true, если по тексту НЕЛЬЗЯ понять, что и где "
    "сломалось, и исполнитель не сможет выехать; тогда заполни "
    "clarification_question_ru и clarification_question_uz — один короткий "
    "вежливый вопрос жителю на каждом языке (иначе пустые строки);\n"
    "- duplicate_of — номер открытой заявки из списка, если это та же самая "
    "проблема в том же месте, иначе null;\n"
    "- confidence — твоя уверенность 0..1 в category и urgency;\n"
    "- reasoning — одна короткая фраза по-русски, почему так (до 200 символов)."
)


INSTRUCTIONS_HEADER = "Правила управляющей компании (обязательны к учёту):"


@lru_cache(maxsize=4)
def _system_prompt(instructions: str = "") -> str:
    """Стабильный системный промпт (кэшируется у провайдера): глоссарий
    категорий — тот же, что у Group Intake; в конце — правила УК со страницы
    «Правила ИИ» (``ai.triage_instructions``), если заданы."""
    from uk_management_bot.services.group_intake.classifier import (
        _GLOSSARY_RULES,
        _category_glossary,
    )

    base = f"{_BASE_PROMPT}\n\nГлоссарий категорий:\n{_category_glossary()}\n\n{_GLOSSARY_RULES}"
    return f"{base}\n\n{INSTRUCTIONS_HEADER}\n{instructions}" if instructions else base


def _user_content(text: str, category: Optional[str], lang: str,
                  open_same_address: Sequence[OpenRequest]) -> str:
    lines = [
        f"Текст заявки: {mask_phones(text or '')[:_TEXT_LIMIT]}",
        f"Категория, выбранная жителем: {category or '—'}",
        f"Язык жителя: {lang}",
    ]
    if open_same_address:
        lines.append("Открытые заявки по этому адресу:")
        lines += [
            f"- {number} [{cat}]: {mask_phones(desc or '')[:200]}"
            for number, cat, desc in open_same_address
        ]
    else:
        lines.append("Открытых заявок по этому адресу нет.")
    return "\n".join(lines)


def parse_llm_triage(payload: Mapping[str, object], *, min_confidence: float,
                     candidates: Sequence[str]) -> Optional[LlmTriage]:
    """Валидация ответа модели в Python: диапазоны, словари, кандидаты дублей.

    Битый payload → None. Уверенность ниже порога → категория/срочность/дубль
    отбрасываются, но просьба уточнить с вопросом ОСТАЁТСЯ: расплывчатый текст
    — ровно тот случай, когда модель не уверена и уточнение нужно (локальная
    проверка 2026-10-28: «что-то не работает» давало 0.5 и терялось целиком).
    Незнакомая категория/срочность → «не менять» (None в поле), а не отказ.
    """
    from uk_management_bot.utils.categories import SELECTABLE_CATEGORY_KEYS, resolve_category_key

    try:
        confidence = float(payload["confidence"])
        raw_category = str(payload["category"] or "").lower()
        raw_urgency = str(payload["urgency"] or "").lower()
        needs_clarification = bool(payload["needs_clarification"])
        question_ru = str(payload.get("clarification_question_ru") or "").strip()
        question_uz = str(payload.get("clarification_question_uz") or "").strip()
        raw_duplicate = payload.get("duplicate_of")
        reasoning = str(payload.get("reasoning") or "").strip()
    except (KeyError, TypeError, ValueError):
        logger.warning("ai_manager.triage: malformed payload keys")
        return None
    if isinstance(payload.get("confidence"), (bool, str)) or not (
        math.isfinite(confidence) and 0.0 <= confidence <= 1.0
    ):
        logger.warning("ai_manager.triage: confidence out of range")
        return None
    confident = confidence >= min_confidence
    if not confident:
        logger.info("ai_manager.triage: confidence %.2f below %.2f — only clarification kept",
                    confidence, min_confidence)

    category = resolve_category_key(raw_category) if confident else None
    if category not in SELECTABLE_CATEGORY_KEYS:
        category = None
    urgency = normalize_urgency(raw_urgency) if confident else None
    question = {}
    if needs_clarification and question_ru and question_uz:
        question = {"ru": question_ru[:_QUESTION_LIMIT], "uz": question_uz[:_QUESTION_LIMIT]}
    duplicate_of = (raw_duplicate if confident and isinstance(raw_duplicate, str) and raw_duplicate in candidates
                    else None)
    return LlmTriage(
        category=category,
        urgency=urgency,
        needs_clarification=bool(question),
        clarification_question=question,
        duplicate_of=duplicate_of,
        confidence=confidence,
        reasoning=reasoning[:_REASONING_LIMIT],
    )


def llm_payload_sync(text: str, *, category: Optional[str], lang: str,
                     open_same_address: Sequence[OpenRequest], instructions: str = "") -> Optional[dict]:
    """Сырой ответ модели; None = сбой вызова (таймаут, сеть, refusal, битый
    JSON) — именно это считает предохранитель. Никогда не бросает."""
    try:
        return llm_json_sync(
            system=_system_prompt(instructions),
            user=_user_content(text, category, lang, open_same_address),
            schema=_schema(),
            model=settings.AI_MANAGER_MODEL,
            timeout=settings.AI_MANAGER_LLM_TIMEOUT,
            max_tokens=_MAX_TOKENS,
            effort=settings.AI_MANAGER_EFFORT,
            tag="ai_manager",
        )
    except Exception as e:  # pragma: no cover — клиент не бросает; страховка
        logger.warning("ai_manager.triage: unexpected %s", type(e).__name__)
        return None


def llm_triage_sync(text: str, *, category: Optional[str], lang: str,
                    open_same_address: Sequence[OpenRequest],
                    min_confidence: float, instructions: str = "") -> Optional[LlmTriage]:
    """Вызов + разбор; любой сбой или низкая уверенность → None."""
    payload = llm_payload_sync(text, category=category, lang=lang,
                               open_same_address=open_same_address, instructions=instructions)
    if payload is None:
        return None
    return parse_llm_triage(
        payload, min_confidence=min_confidence,
        candidates=tuple(number for number, _, _ in open_same_address),
    )


def triage_sync(text: str, *, category: Optional[str], lang: str,
                open_same_address: Sequence[OpenRequest],
                min_confidence: float, instructions: str = "",
                extra_keywords: Sequence[str] = ()) -> TriageHints:
    """Оба анализатора; аварийность считается до и независимо от LLM."""
    return TriageHints(
        emergency=detect_emergency(text, extra_keywords),
        llm=llm_triage_sync(text, category=category, lang=lang,
                            open_same_address=open_same_address,
                            min_confidence=min_confidence, instructions=instructions),
    )
