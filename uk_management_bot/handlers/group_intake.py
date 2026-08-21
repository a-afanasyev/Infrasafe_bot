"""Group Intake: приём заявок из ТГ-групп жителей (план rev.3, v1 — residents).

Роутер подключается ПЕРВЫМ и через root-фильтр chat.type поглощает ЛЮБОЕ
групповое сообщение (catch-all): guard-цепочка внутри хендлера, групповые
тексты/команды не проваливаются в приватные хендлеры. Осознанное следствие:
бот перестаёт отвечать на команды в группах.

Сообщение в группе — НЕ заявка. Заявка возникает только после «Да» автора,
успешного save_request и номера в ответе. Болтовня/ошибки → тишина
(закреплённое сообщение группы объясняет «нет номера — нет заявки»).

AUD3-37: хендлеры не объявляют db — БД только через run_db-юниты;
``_db`` — keyword-only тестовый seam.
"""
import logging
from dataclasses import dataclass
from typing import Optional

from aiogram import Bot, F, Router
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy import select
from sqlalchemy.orm import contains_eager

from uk_management_bot.config.settings import settings
from uk_management_bot.database.models import (
    Apartment,
    Building,
    MonitoredGroup,
    UserApartment,
    Yard,
)
from uk_management_bot.database.models.audit import AuditLog
from uk_management_bot.database.models.monitored_group import GROUP_KIND_RESIDENTS
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.user import User
from uk_management_bot.database.session import run_db
from uk_management_bot.services.group_intake import pending
from uk_management_bot.services.group_intake.classifier import (
    ClassificationResult,
    Outcome,
    classify_message,
)
from uk_management_bot.services.group_intake.prefilter import prefilter
from uk_management_bot.services.request_address import (
    AddressResolutionError,
    format_building_address,
    resolve_request_address_sync,
)
from uk_management_bot.utils.auth_helpers import get_user_roles
from uk_management_bot.utils.helpers import get_text

logger = logging.getLogger(__name__)

router = Router(name="group_intake")
# Root-фильтры: message — только групповые чаты (приватные апдейты роутер не
# проходят и идут дальше по цепочке); callback_query — только наш префикс.
router.message.filter(F.chat.type.in_({"group", "supergroup"}))
router.callback_query.filter(F.data.startswith("gint:"))

# Единый лимит текста кандидата: префильтр, LLM, pending и описание заявки
# работают с ОДНИМ значением (= MAX_DESCRIPTION_LENGTH заявки).
MAX_TEXT_LEN = 2000

CB_YES = "gint:yes"
CB_NO = "gint:no"
CB_OTHER = "gint:other"

# Порядок «шага вниз» при отказе резолвера на уровне scope: от широкого к
# квартире. apartment-уровень — последняя опора; отказ на нём = адреса нет.
_SCOPE_LEVELS = {
    "yard": ("yard", "building", "apartment"),
    "building": ("building", "apartment"),
    "apartment": ("apartment",),
    "unknown": ("apartment",),
}


def _bot_link() -> str:
    return f"https://t.me/{settings.BOT_USERNAME}"


def _deeplink() -> str:
    return f"https://t.me/{settings.BOT_USERNAME}?start=group"


# ───────────────────────── sync-юниты (run_db) ─────────────────────────


def _load_group_sync(db, chat_id: int) -> Optional[dict]:
    """Реестр читается из БД на каждом сообщении — БЕЗ локального кэша:
    api (CRUD реестра) и app — разные процессы, инвалидировать кэш некому."""
    group = (
        db.query(MonitoredGroup).filter(MonitoredGroup.chat_id == chat_id).first()
    )
    if group is None:
        return None
    return {"kind": group.kind, "is_active": bool(group.is_active)}


@dataclass(frozen=True)
class _Gate:
    """Исход гейта автора: ok | no_user | no_role | no_phone | no_address."""

    status: str
    lang: str = "ru"
    address: Optional[dict] = None  # {type, id, label_public, label_full}


def _pick_apartment(rows: list, hint: Optional[str]):
    """Выбор квартиры из approved-цепочек: hint однозначно матчится → она;
    иначе is_primary; далее requested_at DESC, id DESC (продуктовое
    ограничение — адрес виден в промпте, автор жмёт «Нет»/«Другой адрес»)."""
    if hint:
        needle = hint.strip().lower()
        if needle:
            matched = [
                (apt, ua)
                for apt, ua in rows
                if apt.building and needle in (apt.building.address or "").lower()
            ]
            if len({apt.id for apt, _ua in matched}) == 1:
                return matched[0][0]

    def _recency(pair):
        _apt, ua = pair
        ts = ua.requested_at.timestamp() if ua.requested_at else 0.0
        return (ts, ua.id)

    primaries = [pair for pair in rows if pair[1].is_primary]
    pool = primaries or rows
    return max(pool, key=_recency)[0]


def _public_label(level: str, apartment, lang: str) -> str:
    """Публичная форма адреса для промпта в группе — БЕЗ номера квартиры."""
    if level == "apartment":
        return get_text("group_intake.address_public_apartment", language=lang).format(
            building=apartment.building.address if apartment.building else "?"
        )
    if level == "building":
        return format_building_address(apartment.building)
    return apartment.building.yard.name if apartment.building and apartment.building.yard else "?"


def _select_address_sync(db, user_db_id: int, scope: str, hint: Optional[str], lang: str) -> Optional[dict]:
    rows = db.execute(
        select(Apartment, UserApartment)
        .join(UserApartment, UserApartment.apartment_id == Apartment.id)
        .join(Apartment.building)
        .join(Building.yard)
        .options(contains_eager(Apartment.building).contains_eager(Building.yard))
        .where(
            UserApartment.user_id == user_db_id,
            UserApartment.status == "approved",
            Apartment.is_active.is_(True),
            Building.is_active.is_(True),
            Yard.is_active.is_(True),
        )
    ).all()
    if not rows:
        return None

    apartment = _pick_apartment(rows, hint)
    level_ids = {
        "apartment": apartment.id,
        "building": apartment.building_id,
        "yard": apartment.building.yard_id if apartment.building else None,
    }
    for level in _SCOPE_LEVELS.get(scope, _SCOPE_LEVELS["unknown"]):
        address_id = level_ids[level]
        if address_id is None:
            continue
        try:
            resolved = resolve_request_address_sync(
                db, user_db_id, "applicant", level, address_id
            )
        except AddressResolutionError:
            continue  # отказ на уровне → шаг вниз
        return {
            "type": level,
            "id": address_id,
            "label_public": _public_label(level, apartment, lang),
            "label_full": resolved.canonical_address,
        }
    return None


def _author_gate_sync(db, telegram_id: int, scope: str, hint: Optional[str]) -> _Gate:
    user = db.query(User).filter(User.telegram_id == telegram_id).first()
    if user is None or user.status != "approved" or user.deleted_at is not None:
        # нет аккаунта / pending: приглашение. blocked/deleted сюда не доходят
        # (auth-middleware, тихий group-path) — ветка страховочная.
        return _Gate(status="no_user")
    lang = user.language or "ru"
    if "applicant" not in get_user_roles(user):
        return _Gate(status="no_role", lang=lang)
    if not user.phone:
        return _Gate(status="no_phone", lang=lang)
    address = _select_address_sync(db, user.id, scope, hint, lang)
    if address is None:
        return _Gate(status="no_address", lang=lang)
    return _Gate(status="ok", lang=lang, address=address)


def _regate_sync(db, chat_id: int, telegram_id: int, candidate: dict) -> bool:
    """Ре-гейт при «Да»: группа всё ещё активна и residents (и kind не менялся
    за жизнь кандидата), автор всё ещё approved applicant с телефоном.
    Адрес ре-валидируется дальше внутри save_request_sync."""
    group = db.query(MonitoredGroup).filter(MonitoredGroup.chat_id == chat_id).first()
    if group is None or not group.is_active or group.kind != GROUP_KIND_RESIDENTS:
        return False
    if candidate.get("kind") != group.kind:
        return False
    user = db.query(User).filter(User.telegram_id == telegram_id).first()
    if user is None or user.status != "approved" or user.deleted_at is not None:
        return False
    if "applicant" not in get_user_roles(user) or not user.phone:
        return False
    return True


def _audit_created_sync(db, number: str, chat_id: int, source_message_id: int, telegram_id: int) -> None:
    request = db.query(Request).filter(Request.request_number == number).first()
    db.add(
        AuditLog(
            user_id=request.user_id if request else None,
            telegram_user_id=telegram_id,
            action="request.created_from_group",
            details={
                "request_number": number,
                "chat_id": chat_id,
                "source_message_id": source_message_id,
            },
        )
    )
    db.commit()


# ───────────────────────── message-фаза ─────────────────────────


def candidate_text(message: Message) -> tuple[str, bool]:
    """Единый текст кандидата (text|caption, strip, обрезка) + флаг обрезки."""
    raw = (message.text or message.caption or "").strip()
    return raw[:MAX_TEXT_LEN], len(raw) > MAX_TEXT_LEN


async def _send_invite(message: Message, key: str, lang: str) -> None:
    """Приглашение в личный бот — не чаще 1/час на пользователя (cooldown)."""
    if not await pending.invite_allowed(message.from_user.id):
        return
    await message.reply(
        get_text(f"group_intake.{key}", language=lang).format(link=_deeplink())
    )


def _confirm_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=get_text("group_intake.btn_yes", language=lang), callback_data=CB_YES
                ),
                InlineKeyboardButton(
                    text=get_text("group_intake.btn_no", language=lang), callback_data=CB_NO
                ),
            ],
            [
                InlineKeyboardButton(
                    text=get_text("group_intake.btn_other", language=lang),
                    callback_data=CB_OTHER,
                )
            ],
        ]
    )


@router.message()
async def group_message_entry(message: Message, bot: Bot, *, _db=None) -> None:
    """Catch-all групповых сообщений: guard-цепочка → LLM → промпт/тишина."""
    if not settings.GROUP_INTAKE_ENABLED:
        return
    if message.from_user is None or message.from_user.is_bot or message.via_bot:
        return

    text, truncated = candidate_text(message)
    if not text or text.startswith("/"):
        return
    has_photo = bool(message.photo)
    if not prefilter(text, has_photo=has_photo):
        return

    group = await run_db(lambda s: _load_group_sync(s, message.chat.id), db=_db)
    if group is None or not group["is_active"] or group["kind"] != GROUP_KIND_RESIDENTS:
        # staff-группы — фаза 2 (решение владельца по модели приёмки): тишина.
        return

    if not await pending.mark_seen(message.chat.id, message.message_id):
        return
    if not await pending.llm_allowed(message.chat.id):
        logger.warning("group_intake.rate_limited: chat_id=%s", message.chat.id)
        return

    result: ClassificationResult = await classify_message(text)
    if result.outcome is not Outcome.REQUEST:
        # NOT_REQUEST и PROCESSING_ERROR в группе неразличимы (тишина);
        # различие живёт в логах classifier'а.
        return

    gate: _Gate = await run_db(
        lambda s: _author_gate_sync(
            s, message.from_user.id, result.location_scope, result.address_hint
        ),
        db=_db,
    )
    if gate.status == "no_user":
        lang = (message.from_user.language_code or "ru")
        await _send_invite(message, "invite_register", lang)
        return
    if gate.status == "no_role":
        await _send_invite(message, "invite_no_role", gate.lang)
        return
    if gate.status == "no_phone":
        await _send_invite(message, "invite_no_phone", gate.lang)
        return
    if gate.status == "no_address":
        await _send_invite(message, "invite_address", gate.lang)
        return

    lang = gate.lang
    prompt = get_text("group_intake.confirm_prompt", language=lang).format(
        category=_category_display(result.category, lang),
        urgency=_urgency_display(result.urgency, lang),
        address=gate.address["label_public"],
    )
    if truncated:
        prompt += get_text("group_intake.truncated_note", language=lang)

    sent = await message.reply(prompt, reply_markup=_confirm_keyboard(lang))

    photo_file_id = message.photo[-1].file_id if message.photo else None
    stored = await pending.store_candidate(
        message.chat.id,
        sent.message_id,
        {
            "kind": GROUP_KIND_RESIDENTS,
            "author_id": message.from_user.id,
            "source_message_id": message.message_id,
            "text": text,
            "truncated": truncated,
            "category": result.category,
            "urgency": result.urgency,
            "confidence": result.confidence,
            "location_scope": result.location_scope,
            "photo_file_id": photo_file_id,
            "selected_address": gate.address,
            "lang": lang,
        },
    )
    if not stored:
        # Запись упала ПОСЛЕ отправки промпта: снять клавиатуру, чтобы кнопки
        # не вели в guaranteed-expired.
        try:
            await sent.edit_reply_markup(reply_markup=None)
        except Exception:
            pass


def _category_display(category: Optional[str], lang: str) -> str:
    from uk_management_bot.keyboards.requests import get_category_display

    return get_category_display(category or "other", lang)


def _urgency_display(urgency: Optional[str], lang: str) -> str:
    from uk_management_bot.keyboards.requests import get_urgency_display

    return get_urgency_display(urgency or "low", lang)


# ───────────────────────── callback-фаза ─────────────────────────


@router.callback_query()
async def group_intake_callback(callback: CallbackQuery, bot: Bot, *, _db=None) -> None:
    """Кнопки промпта. Контракт: ровно один callback.answer() на нажатие."""
    lang_fallback = callback.from_user.language_code or "ru"
    if not settings.GROUP_INTAKE_ENABLED or callback.message is None:
        await callback.answer()
        return

    chat_id = callback.message.chat.id
    prompt_message_id = callback.message.message_id

    candidate = await pending.get_candidate(chat_id, prompt_message_id)
    if candidate is None:
        await callback.answer(
            get_text("group_intake.expired", language=lang_fallback), show_alert=True
        )
        return

    lang = candidate.get("lang") or lang_fallback
    if callback.from_user.id != candidate.get("author_id"):
        await callback.answer(
            get_text("group_intake.not_author", language=lang), show_alert=True
        )
        return

    # Автор: пустой answer сразу, дальше работа (редактирование промпта).
    await callback.answer()

    action = (callback.data or "").split(":", 1)[-1]
    if action == "no":
        await pending.pop_candidate(chat_id, prompt_message_id)
        await callback.message.edit_text(get_text("group_intake.cancelled", language=lang))
        return
    if action == "other":
        await pending.pop_candidate(chat_id, prompt_message_id)
        await callback.message.edit_text(
            get_text("group_intake.other_address", language=lang).format(link=_deeplink())
        )
        return
    if action != "yes":
        return

    # GETDEL — идемпотентность двойного «Да»: второй pop получает None.
    candidate = await pending.pop_candidate(chat_id, prompt_message_id)
    if candidate is None:
        await callback.message.edit_text(get_text("group_intake.expired", language=lang))
        return

    allowed = await run_db(
        lambda s: _regate_sync(s, chat_id, callback.from_user.id, candidate), db=_db
    )
    if not allowed:
        await callback.message.edit_text(get_text("group_intake.expired", language=lang))
        return

    from uk_management_bot.handlers.requests.create import save_request

    photo_file_id = candidate.get("photo_file_id")
    data = {
        "category": candidate["category"],
        "urgency": candidate["urgency"],
        "address_type": candidate["selected_address"]["type"],
        "address_id": candidate["selected_address"]["id"],
        "description": candidate["text"],
        "media_files": [photo_file_id] if photo_file_id else [],
        "source_chat_id": chat_id,
        "source_message_id": candidate.get("source_message_id"),
    }
    request_number = await save_request(
        data, callback.from_user.id, _db, bot, source="group", role="applicant"
    )
    if not request_number:
        # Честный error-текст (не тишина): создание могло упасть на
        # ре-резолве адреса, валидации или БД.
        await callback.message.edit_text(
            get_text("group_intake.error", language=lang).format(link=_bot_link())
        )
        return

    await callback.message.edit_text(
        get_text("group_intake.created", language=lang).format(
            number=request_number, link=_bot_link()
        )
    )
    # Audit-строка — best-effort, поверх транзакционной provenance в requests.
    try:
        await run_db(
            lambda s: _audit_created_sync(
                s,
                request_number,
                chat_id,
                candidate.get("source_message_id"),
                callback.from_user.id,
            ),
            db=_db,
        )
    except Exception as e:
        logger.warning("group_intake: audit write failed: %s", type(e).__name__)
