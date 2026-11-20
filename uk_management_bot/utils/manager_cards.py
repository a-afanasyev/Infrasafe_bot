"""Карточка-решение менеджеру: текст события + кнопки по состоянию заявки.

Менеджер работает в чате бота, без мини-приложения, поэтому событие, которое
требует его решения, приходит сразу с кнопками. Кнопки — СУЩЕСТВУЮЩИЕ callback'и
(подтверждение, возврат, назначение, уточнение, отклонение): их обработчики уже
перечитывают заявку и идут через канон, так что карточка не добавляет ни
второго пути записи, ни новых обработчиков.

Не в `keyboards/`: разметку шлёт сервисный слой (`workflow_notifications`),
которому импорт UI-пакета бота запрещён гейтом A9-P2-10 — по той же причине,
что и у `utils/twa_links.py`.
"""
from __future__ import annotations

import html
import re
from typing import Optional

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from uk_management_bot.services.request_number_service import REQUEST_NUMBER_CORE
from uk_management_bot.utils.helpers import get_text
from uk_management_bot.utils.request_workflow.projections import normalize_status
from uk_management_bot.utils.request_workflow.types import STATUS_RETURNED
from uk_management_bot.utils.workflow_predicates import (
    is_awaiting_manager,
    is_reassignable,
    is_unassigned_new,
)

REVIEW_KEY = "notifications.manager.review"
RETURNED_KEY = "notifications.manager.returned"
UNASSIGNED_KEY = "notifications.manager.unassigned"
#: Ключи текстов, к которым прилагается клавиатура решения.
MANAGER_CARD_KEYS = frozenset({REVIEW_KEY, RETURNED_KEY, UNASSIGNED_KEY})

_MAX_ADDRESS = 150
_MAX_DESCRIPTION = 300


def _clip(value: Optional[str], limit: int) -> str:
    value = value or ""
    return value if len(value) <= limit else value[: limit - 1] + "…"


def _button(text_key: str, language: str, callback_data: str,
            style: Optional[str] = None) -> InlineKeyboardButton:
    """Кнопка с цветом Bot API 9.4 (`danger`/`success`/`primary`); None — обычная."""
    extra = {"style": style} if style else {}
    return InlineKeyboardButton(
        text=get_text(text_key, language=language), callback_data=callback_data, **extra)


def manager_card_markup(request, language: str) -> InlineKeyboardMarkup:
    """Кнопки решения. Состояние заявки важнее события, вызвавшего карточку:
    выполненная просроченная заявка предлагает проверку, а не переназначение.
    """
    number = request.request_number
    canon = normalize_status(request)
    if is_awaiting_manager(request):
        # По кнопке в ряд: «Подтвердить выполнение» рядом с «Вернуть в работу»
        # на телефоне обрезалась до «Подтвердить вып…» (живая проверка 2026-11-19).
        rows = [
            [_button("admin.keyboards.confirm_completion", language, f"confirm_completed_{number}", "success")],
            [_button("admin.keyboards.return_to_work", language, f"return_to_work_{number}")],
        ]
    elif canon == STATUS_RETURNED:
        rows = [
            [_button("admin.keyboards.reconfirm", language, f"reconfirm_completed_{number}", "success")],
            [_button("admin.keyboards.return_to_work", language, f"return_to_work_{number}")],
        ]
    elif is_unassigned_new(request):
        rows = [
            [_button("admin.keyboards.assign_duty_specialist", language, f"req_reassign_duty_{number}", "success")],
            [_button("admin.keyboards.assign_specific_executor", language, f"req_reassign_pick_{number}", "primary")],
            [
                _button("admin.keyboards.clarify", language, f"clarify_{number}"),
                _button("admin.keyboards.decline", language, f"mgr_deny_{number}", "danger"),
            ],
        ]
    elif is_reassignable(request):
        rows = [[_button("admin.keyboards.reassign_request", language, f"req_reassign_menu_{number}", "primary")]]
    else:
        rows = []
    rows.append([_button("notifications.workflow.btn_open_request", language, f"mview_{number}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


#: Telegram допускает до 100 кнопок в сообщении; дайджесту хватает меньшего,
#: а длинная простыня кнопок под текстом нечитаема.
_MAX_DIGEST_BUTTONS = 20


def open_requests_markup(text: str) -> Optional[InlineKeyboardMarkup]:
    """Кнопки «открыть заявку» для дайджеста: по номеру на каждую упомянутую.

    Номера берутся из самого текста (формат `YYMMDD-NNN`), а не из параллельного
    списка: дайджест собирается строками из разных мест, и такой список
    разъехался бы с текстом при первой же вставке заголовка. Кнопка —
    существующий `mview_<номер>`: карточка откроется с действиями по
    фактическому состоянию заявки.
    """
    numbers = list(dict.fromkeys(re.findall(rf"(?<![\d-])({REQUEST_NUMBER_CORE})(?![\d-])", text)))
    if not numbers:
        return None
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"📂 #{number}", callback_data=f"mview_{number}")]
        for number in numbers[:_MAX_DIGEST_BUTTONS]
    ])


def manager_card_text(text_key: str, language: str, request, category_label: str) -> str:
    """Текст карточки. Адрес, описание и причина — пользовательский ввод:
    обрезаются ДО `html.escape`, иначе entity рвётся пополам и Telegram
    отвечает 400. ``category_label`` — уже экранированная подпись категории.
    """
    text = get_text(
        text_key,
        language=language,
        request_number=request.request_number,
        category=category_label,
        address=html.escape(_clip(request.address, _MAX_ADDRESS)),
        description=html.escape(_clip(getattr(request, "description", None), _MAX_DESCRIPTION)),
    )
    reason = getattr(request, "return_reason", None)
    if text_key == RETURNED_KEY and reason:
        text += get_text("notifications.workflow.return_reason_line", language=language,
                         reason=html.escape(_clip(reason, _MAX_DESCRIPTION)))
    return text
