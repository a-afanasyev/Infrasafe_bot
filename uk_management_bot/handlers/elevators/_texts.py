"""Тексты бота лифтёра (Ф5, T10): локаль ``elevators.bot.*``, HTML-безопасно.

Всё, что пришло из БД (адреса, подписи лифта, статусы), проходит
``html.escape`` — сообщения уходят с ``parse_mode="HTML"``. Тексты доменных
ошибок сюда не попадают: вердикт юнита маппится на ключ локали (``deny_text``).
"""

from __future__ import annotations

import html
from datetime import date
from typing import Optional

from uk_management_bot.services.elevator_service import status_label
from uk_management_bot.utils.business_time import fmt_date, fmt_datetime
from uk_management_bot.utils.helpers import get_text

from ._units import BuildingsView, CardView, CompleteOutcome, ElevatorsView, StatusOutcome

KEY = "elevators.bot."

STATUS_EMOJI: dict[str, str] = {
    "working": "✅",
    "not_working": "⛔",
    "under_repair": "🛠",
    "maintenance": "🔧",
}
NO_STATUS_EMOJI = "⚪"

# Вердикт юнита → ключ локали отказа/ошибки. Ключи вне ``elevators.bot`` — полные.
_DENY_KEYS: dict[str, str] = {
    "disabled": KEY + "disabled",
    "no_access": "auth.no_access",
    "no_role": "auth.no_access",
    "no_spec": KEY + "no_spec",
    "request_mismatch": KEY + "request_mismatch",
    "not_found": KEY + "not_found",
    "rejected": KEY + "status_rejected",
    "state_error": KEY + "occ_state_error",
    "invalid": KEY + "occ_invalid",
}


def t(key: str, language: str, **kwargs) -> str:
    """``get_text`` с префиксом ``elevators.bot.``."""
    return get_text(KEY + key, language=language, **kwargs)


def deny_text(verdict: str, language: str) -> str:
    return get_text(_DENY_KEYS.get(verdict, KEY + "error"), language=language)


def status_emoji(status: Optional[str]) -> str:
    return STATUS_EMOJI.get(status or "", NO_STATUS_EMOJI)


def kind_label(kind: str, language: str) -> str:
    return t(f"kind.{kind}", language)


def elevator_button(entrance: int, number: int, status: Optional[str], language: str) -> str:
    return t("elevator_button", language, emoji=status_emoji(status), entrance=entrance,
             number=number, status=status_label(status, language))


def buildings_title(view: BuildingsView, language: str) -> str:
    return t("yard_title", language, yard=html.escape(view.yard_name))


def elevators_title(view: ElevatorsView, language: str) -> str:
    return t("building_title", language, address=html.escape(view.address))


def _since(view: CardView, language: str) -> str:
    return fmt_datetime(view.status_since) if view.status_since else t("since_unknown", language)


def _availability(view: CardView, language: str) -> str:
    if view.availability is None:
        return t("availability_unknown", language)
    return f"{view.availability * 100:.0f}%"


def _next(view: CardView, language: str) -> str:
    if view.next_kind is None or view.next_due is None:
        return t("next_none", language)
    return t("next_item", language, kind=kind_label(view.next_kind, language),
             date=fmt_date(view.next_due))


def card_text(view: CardView, language: str) -> str:
    return t(
        "card", language,
        label=html.escape(view.label),
        status=html.escape(status_label(view.status, language)),
        since=_since(view, language),
        availability=_availability(view, language),
        next=html.escape(_next(view, language)),
        open=view.open_requests,
    )


def status_outcome_text(outcome: StatusOutcome, sent: int, language: str) -> str:
    """Только для вердиктов changed/unchanged; остальное — ``deny_text``."""
    if outcome.verdict == "unchanged":
        return t("status_unchanged", language,
                 status=html.escape(status_label(outcome.new_status, language)))
    return t(
        "status_changed", language,
        old=html.escape(status_label(outcome.old_status, language)),
        new=html.escape(status_label(outcome.new_status, language)),
        count=sent,
    )


def occurrence_button(kind: str, due_on: date, overdue: bool, language: str) -> str:
    mark = t("occ_overdue_mark", language) if overdue else ""
    return t("occ_button", language, overdue=mark, kind=kind_label(kind, language), date=fmt_date(due_on))


def occ_done_text(outcome: CompleteOutcome, language: str) -> str:
    next_text = fmt_date(outcome.next_due) if outcome.next_due else t("next_none", language)
    return t("occ_done", language, next=next_text)


def repair_created_text(request_number: str, language: str) -> str:
    return t("repair_created", language, number=html.escape(request_number))
