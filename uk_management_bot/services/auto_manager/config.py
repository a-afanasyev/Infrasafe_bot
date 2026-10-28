"""Общая валидация + load/save singleton-конфига «автоматического менеджера».

`validate_config` — чистая функция (без I/O), переиспользуемая и Pydantic-
схемой API (в валидаторе), и ботом (сырой dict из шедулера/хендлера) — должна
вести себя идентично в обоих местах.

Sync-варианты (`load_config_sync`/`save_config_sync`, `Session`) — для бота
(шедулер-job, хендлер меню). Async-варианты (`load_config`/`save_config`,
`AsyncSession`) — для FastAPI-роутера дашборда. Паттерн load/save — клон
board_config (services/board_config/service.py, router.py): толерантность к
отсутствующей строке/таблице (fallback на дефолт), upsert по id=CONFIG_ROW_ID.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from uk_management_bot.database.models.auto_manager_config import AutoManagerConfig
from uk_management_bot.utils.business_time import BUSINESS_TZ

logger = logging.getLogger(__name__)

CONFIG_ROW_ID = 1

DEFAULT_CONFIG: dict = {
    "enabled": False,
    "mode": "rule",
    "window_start": "20:00",
    "window_end": "08:00",
    # ARCH-116: дефолт берём из канона бизнес-зоны — значение остаётся
    # настраиваемым (окно авто-менеджера может жить в другой зоне), но вторая
    # захардкоженная копия названия зоны в репо не появляется.
    "timezone": str(BUSINESS_TZ),
    "max_requests_per_run": 10,
    # Нормативы сроков аналитики (часы от создания до сдачи работы) по
    # срочности. Не про авто-менеджер, но это единственный настраиваемый
    # singleton-конфиг заявок: отдельная таблица ради четырёх чисел не нужна.
    "sla_hours": {"critical": 4, "high": 24, "medium": 72, "low": 168},
    # Режим «ИИ-менеджер» (mode="ai"): порог уверенности LLM-триажа, ниже
    # которого подсказки не применяются (rule-путь); разрешение задавать
    # жителю уточняющий вопрос; поиск дублей по открытым заявкам адреса.
    "ai": {
        "min_confidence": 0.7, "clarify_enabled": True, "dedup_enabled": True,
        # Правила УК свободным текстом — в системный промпт триажа заявок /
        # анализа новостей об отключениях (страница «Правила ИИ»).
        "triage_instructions": "",
        "news_instructions": "",
        # Дополнительно к базовым EMERGENCY_KEYWORDS (ai_manager/triage.py —
        # неотключаемы): подстроки в нижнем регистре, совпадение → critical.
        "extra_emergency_keywords": [],
        # Переопределения текстов пингов: {"sla.executor_overdue": {"ru": …,
        # "uz": …}} — контракт в ai_manager/templates.py.
        "templates": {},
    },
    # SLA-лестница ИИ-менеджера (фаза 2, только при mode="ai"). Часы, int;
    # 0 = ступень/трек выключены. `ladder` — смещения в часах от момента
    # просрочки «В работе»: DM исполнителю → staff-группа → менеджер →
    # переназначение дежурному.
    "sla": {
        "in_progress_max": {"low": 72, "medium": 48, "high": 12, "critical": 2},
        "clarification_max": 48,
        "executed_unconfirmed_max": 24,
        "completed_unaccepted_days": 3,
        "critical_unassigned_minutes": 30,
        "ladder": {"remind_executor": 0, "staff_group": 2, "manager": 4, "reassign": 8},
        # Выключенная ступень считается пройденной: пинг не уходит, следующая
        # срабатывает по своему смещению.
        "ladder_enabled": {"remind_executor": True, "staff_group": True, "manager": True, "reassign": True},
        # Публичные статусы в чат дома: выключатель и минимальная срочность.
        "public_status": {"enabled": True, "min_urgency": "critical"},
    },
}

_INSTRUCTIONS_MAX = 2000
_KEYWORD_MIN = 3   # подстрочное совпадение: «а»/«ab» есть почти в любом тексте → всё critical
_KEYWORD_MAX = 50
_KEYWORDS_MAX = 100
_PUBLIC_URGENCIES = ("critical", "high")

#: Норматив в часах: от часа до года — защита от опечаток вида 0 или 99999.
SLA_HOURS_MAX = 8784

# Строгий HH:MM: два ровно разряда часов и минут. Сам по себе пропускает
# "99:99" (не валидное время) — поэтому дополнительно нужен strptime ниже.
_TIME_RE = re.compile(r"\d{2}:\d{2}")
_VALID_MODES = {"rule", "ai"}


def _validate_time(value: object, field_name: str) -> str:
    """Строгий HH:MM: regex (2+2 цифры) И strptime (реальное время).

    Regex один пропустил бы "99:99" (2 цифры на 2 цифры, но не время).
    strptime один пропустил бы "1:2"/"1:02" (%H/%M не требуют ведущего нуля
    при парсинге) — оба условия обязательны.
    """
    if not isinstance(value, str) or not _TIME_RE.fullmatch(value):
        raise ValueError(f"{field_name}: ожидается строгий формат HH:MM, получено {value!r}")
    try:
        datetime.strptime(value, "%H:%M")
    except ValueError as e:
        raise ValueError(f"{field_name}: невалидное время {value!r}") from e
    return value


def _validate_sla_hours(raw: object) -> dict:
    """Частичный dict поверх дефолта; каждый норматив — целые часы 1..SLA_HOURS_MAX."""
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ValueError(f"sla_hours: ожидается dict, получено {raw!r}")
    defaults = DEFAULT_CONFIG["sla_hours"]
    unknown = sorted(set(raw) - set(defaults))
    if unknown:
        raise ValueError(f"sla_hours: неизвестные срочности {unknown}")
    merged = {**defaults, **raw}
    for key, hours in merged.items():
        if isinstance(hours, bool) or not isinstance(hours, int) or not 1 <= hours <= SLA_HOURS_MAX:
            raise ValueError(f"sla_hours.{key}: ожидается целое 1..{SLA_HOURS_MAX}, получено {hours!r}")
    return merged


def _validate_ai(raw: object) -> dict:
    """Частичный dict поверх дефолта ``ai``: порог 0..1, флаги — bool."""
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ValueError(f"ai: ожидается dict, получено {raw!r}")
    defaults = DEFAULT_CONFIG["ai"]
    unknown = sorted(set(raw) - set(defaults))
    if unknown:
        raise ValueError(f"ai: неизвестные ключи {unknown}")
    merged = {**defaults, **raw}
    threshold = merged["min_confidence"]
    if isinstance(threshold, bool) or not isinstance(threshold, (int, float)) or not 0.0 <= threshold <= 1.0:
        raise ValueError(f"ai.min_confidence: ожидается число 0..1, получено {threshold!r}")
    for key in ("clarify_enabled", "dedup_enabled"):
        if not isinstance(merged[key], bool):
            raise ValueError(f"ai.{key}: ожидается bool, получено {merged[key]!r}")
    # Локальный импорт: ai_manager импортирует этот модуль (load_config_sync).
    from uk_management_bot.services.ai_manager.templates import validate_overrides

    return {
        **merged, "min_confidence": float(threshold),
        "triage_instructions": _validate_instructions(merged["triage_instructions"], "ai.triage_instructions"),
        "news_instructions": _validate_instructions(merged["news_instructions"], "ai.news_instructions"),
        "extra_emergency_keywords": _validate_keywords(merged["extra_emergency_keywords"]),
        "templates": validate_overrides(merged["templates"]),
    }


def _validate_instructions(value: object, field_name: str) -> str:
    if not isinstance(value, str) or len(value.strip()) > _INSTRUCTIONS_MAX:
        raise ValueError(f"{field_name}: ожидается строка до {_INSTRUCTIONS_MAX} символов")
    return value.strip()


def _validate_keywords(raw: object) -> list[str]:
    """strip+lower, дедуп, без базовых слов (они неотключаемы и уже действуют)."""
    from uk_management_bot.services.ai_manager.triage import EMERGENCY_KEYWORDS

    if not isinstance(raw, list) or any(not isinstance(k, str) for k in raw):
        raise ValueError("ai.extra_emergency_keywords: ожидается список строк")
    seen: list[str] = []
    for word in (k.strip().lower() for k in raw):
        if not word:
            continue
        if not _KEYWORD_MIN <= len(word) <= _KEYWORD_MAX:
            raise ValueError(f"ai.extra_emergency_keywords: слово {word!r} — ожидается {_KEYWORD_MIN}..{_KEYWORD_MAX} символов")
        if word not in seen and word not in EMERGENCY_KEYWORDS:
            seen.append(word)
    if len(seen) > _KEYWORDS_MAX:
        raise ValueError(f"ai.extra_emergency_keywords: не более {_KEYWORDS_MAX} слов")
    return seen


def _non_negative_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name}: ожидается целое ≥ 0, получено {value!r}")
    return value


def _merge_block(raw: object, defaults: dict, field_name: str) -> dict:
    """Частичный dict поверх дефолтов; неизвестные ключи — ошибка."""
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ValueError(f"{field_name}: ожидается dict, получено {raw!r}")
    unknown = sorted(set(raw) - set(defaults))
    if unknown:
        raise ValueError(f"{field_name}: неизвестные ключи {unknown}")
    return {**defaults, **raw}


def _merge_int_block(raw: object, defaults: dict, field_name: str) -> dict:
    """Частичный dict целых ≥ 0 поверх дефолтов."""
    merged = _merge_block(raw, defaults, field_name)
    return {k: _non_negative_int(v, f"{field_name}.{k}") for k, v in merged.items()}


def _merge_bool_block(raw: object, defaults: dict, field_name: str) -> dict:
    merged = _merge_block(raw, defaults, field_name)
    for k, v in merged.items():
        if not isinstance(v, bool):
            raise ValueError(f"{field_name}.{k}: ожидается bool, получено {v!r}")
    return merged


def _validate_public_status(raw: object) -> dict:
    merged = _merge_block(raw, DEFAULT_CONFIG["sla"]["public_status"], "sla.public_status")
    if not isinstance(merged["enabled"], bool):
        raise ValueError(f"sla.public_status.enabled: ожидается bool, получено {merged['enabled']!r}")
    if merged["min_urgency"] not in _PUBLIC_URGENCIES:
        raise ValueError(f"sla.public_status.min_urgency: ожидается одно из {_PUBLIC_URGENCIES}")
    return merged


def _validate_sla(raw: object) -> dict:
    """Блок ``sla``: два вложенных уровня (``in_progress_max``, ``ladder``)."""
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ValueError(f"sla: ожидается dict, получено {raw!r}")
    defaults = DEFAULT_CONFIG["sla"]
    unknown = sorted(set(raw) - set(defaults))
    if unknown:
        raise ValueError(f"sla: неизвестные ключи {unknown}")
    merged = {**defaults, **raw}
    return {
        **{k: _non_negative_int(merged[k], f"sla.{k}") for k in (
            "clarification_max", "executed_unconfirmed_max",
            "completed_unaccepted_days", "critical_unassigned_minutes")},
        "in_progress_max": _merge_int_block(
            raw.get("in_progress_max"), defaults["in_progress_max"], "sla.in_progress_max"),
        "ladder": _merge_int_block(raw.get("ladder"), defaults["ladder"], "sla.ladder"),
        "ladder_enabled": _merge_bool_block(raw.get("ladder_enabled"), defaults["ladder_enabled"], "sla.ladder_enabled"),
        "public_status": _validate_public_status(raw.get("public_status")),
    }


def validate_config(raw: dict) -> dict:
    """Чистая валидация + нормализация конфига авто-менеджера.

    Мёрджит `raw` поверх `DEFAULT_CONFIG` (отсутствующие ключи → дефолт), затем
    валидирует каждое поле. Без обращений к БД/сети (шаблоны читают локали через
    lru_cache) — вызывается и из Pydantic-схемы API, и из сырого dict-пути бота;
    обязана вести себя идентично в обоих местах.

    Raises:
        ValueError: конкретное поле не прошло валидацию.
    """
    if not isinstance(raw, dict):
        raise ValueError(f"config: ожидается dict, получено {type(raw).__name__}")

    # Верхний уровень мёржится shallow — вложенные блоки мёржатся каждый
    # поверх своих дефолтов, иначе частичный dict затирал бы их целиком.
    cfg = {**DEFAULT_CONFIG, **raw}
    cfg["sla_hours"] = _validate_sla_hours(raw.get("sla_hours"))
    cfg["ai"] = _validate_ai(raw.get("ai"))
    cfg["sla"] = _validate_sla(raw.get("sla"))

    if not isinstance(cfg["enabled"], bool):
        raise ValueError(f"enabled: ожидается bool, получено {cfg['enabled']!r}")

    if not isinstance(cfg["mode"], str) or cfg["mode"] not in _VALID_MODES:
        raise ValueError(f"mode: ожидается 'rule' или 'ai', получено {cfg['mode']!r}")

    _validate_time(cfg["window_start"], "window_start")
    _validate_time(cfg["window_end"], "window_end")

    if not isinstance(cfg["timezone"], str):
        raise ValueError(f"timezone: ожидается строка, получено {cfg['timezone']!r}")
    try:
        ZoneInfo(cfg["timezone"])
    except ZoneInfoNotFoundError as e:
        raise ValueError(f"timezone: неизвестная IANA-зона {cfg['timezone']!r}") from e

    max_requests = cfg["max_requests_per_run"]
    # bool — подкласс int в Python, исключаем явно (True/False не число заявок).
    if isinstance(max_requests, bool) or not isinstance(max_requests, int):
        raise ValueError(f"max_requests_per_run: ожидается int, получено {max_requests!r}")
    if not (1 <= max_requests <= 50):
        raise ValueError(f"max_requests_per_run: ожидается 1..50, получено {max_requests!r}")

    return cfg


def is_window_active(cfg: dict, now_utc: datetime) -> bool:
    """Активно ли окно авто-менеджера в момент `now_utc` (tz-aware, UTC).

    `cfg` — уже валидированный dict (см. validate_config). Конвертирует
    `now_utc` в `cfg["timezone"]`, берёт time() и сравнивает с window_start/end:
      * start == end        → всегда активно (24/7, явное продуктовое решение).
      * start < end          → активно при start <= t < end (окно в пределах суток).
      * start > end          → активно при t >= start или t < end (окно через полночь).
    """
    tz = ZoneInfo(cfg["timezone"])
    local_time = now_utc.astimezone(tz).time()

    start = datetime.strptime(cfg["window_start"], "%H:%M").time()
    end = datetime.strptime(cfg["window_end"], "%H:%M").time()

    if start == end:
        return True
    if start < end:
        return start <= local_time < end
    return local_time >= start or local_time < end


# ─────────────────────── Sync (бот: шедулер-job, хендлер меню) ───────────────────────

def load_config_sync(db: Session) -> dict:
    """Загрузить конфиг (id=CONFIG_ROW_ID) или отдать дефолт.

    Толерантен к отсутствующей строке (ещё не сохраняли) и к отсутствующей
    таблице (миграция не накатана) — не должен падать вызывающему коду.
    """
    data = DEFAULT_CONFIG
    try:
        row = db.query(AutoManagerConfig).filter(AutoManagerConfig.id == CONFIG_ROW_ID).first()
        if row is not None and row.data:
            data = row.data
    except (OperationalError, ProgrammingError) as e:
        logger.warning("auto_manager_config недоступен, отдаю дефолт: %s", e)

    try:
        return validate_config(data)
    except ValueError as e:
        # Битая/легаси строка в БД не должна ронять шедулер/хендлер — дефолт.
        logger.warning("auto_manager_config.data не проходит валидацию, отдаю дефолт: %s", e)
        return validate_config(DEFAULT_CONFIG)


def is_auto_assign_enabled_sync(db: Session) -> bool:
    """Включено ли автоназначение (флаг `enabled` singleton-конфига).

    Тонкий ридер поверх `load_config_sync` — нужен всем, кто раздаёт заявки
    автоматически, а не только оркестратору авто-менеджера. Отдельная функция,
    а не `load_config_sync(db)["enabled"]` по месту: точек вызова несколько, и
    fail-safe направление обязано быть одинаковым во всех.

    Fail-safe: недоступная таблица/битая строка → `load_config_sync` отдаёт
    дефолт, а в дефолте `enabled=False`. При сломанном конфиге заявки остаются
    «Новая» и достаются человеку — молча раздавать их было бы хуже.
    """
    return bool(load_config_sync(db)["enabled"])


def save_config_sync(db: Session, data: dict, updated_by: int | None = None) -> dict:
    """Валидировать и сохранить конфиг (upsert по id=CONFIG_ROW_ID)."""
    validated = validate_config(data)

    row = db.query(AutoManagerConfig).filter(AutoManagerConfig.id == CONFIG_ROW_ID).first()
    if row is None:
        db.add(AutoManagerConfig(id=CONFIG_ROW_ID, data=validated, updated_by=updated_by))
    else:
        row.data = validated
        row.updated_by = updated_by
    db.commit()

    return validated


# ───────────────────────── Async (API дашборда) ─────────────────────────

async def load_config(db: AsyncSession) -> dict:
    """Асинхронный аналог load_config_sync — тот же fallback-контракт."""
    data = DEFAULT_CONFIG
    try:
        result = await db.execute(
            select(AutoManagerConfig).where(AutoManagerConfig.id == CONFIG_ROW_ID)
        )
        row = result.scalar_one_or_none()
        if row is not None and row.data:
            data = row.data
    except (OperationalError, ProgrammingError) as e:
        logger.warning("auto_manager_config недоступен, отдаю дефолт: %s", e)

    try:
        return validate_config(data)
    except ValueError as e:
        logger.warning("auto_manager_config.data не проходит валидацию, отдаю дефолт: %s", e)
        return validate_config(DEFAULT_CONFIG)


async def is_auto_assign_enabled(db: AsyncSession) -> bool:
    """Асинхронный аналог `is_auto_assign_enabled_sync` — тот же fail-safe."""
    cfg = await load_config(db)
    return bool(cfg["enabled"])


async def save_config(db: AsyncSession, data: dict, updated_by: int | None = None) -> dict:
    """Асинхронный аналог save_config_sync — тот же upsert-по-id контракт."""
    validated = validate_config(data)

    result = await db.execute(
        select(AutoManagerConfig).where(AutoManagerConfig.id == CONFIG_ROW_ID)
    )
    row = result.scalar_one_or_none()
    if row is None:
        db.add(AutoManagerConfig(id=CONFIG_ROW_ID, data=validated, updated_by=updated_by))
    else:
        row.data = validated
        row.updated_by = updated_by
    await db.commit()

    return validated
