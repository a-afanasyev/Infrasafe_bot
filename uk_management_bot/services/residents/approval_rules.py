"""Что требуется от жителя для подтверждения верификации и доступа к системе.

Решение владельца (2026-11-03): телефон и документ на квартиру (право
собственности или договор аренды) обязательны. Правило ОДНО и живёт здесь —
его зовут API (дашборд) и бот, копий нет:

  * верификацию подтверждают, только если загружен документ на квартиру
    либо менеджер отметил, что проверил его очно;
  * аккаунт жителя одобряют (и разблокируют в `approved`), только если есть
    телефон и верификация подтверждена.

Модуль без БД и без сети: на вход — примитивы и ORM-строка пользователя.
"""
from __future__ import annotations

from uk_management_bot.database.models.user_verification import DocumentType
from uk_management_bot.utils.auth_helpers import parse_roles_safe

#: Документы, подтверждающие право жить в квартире.
PROPERTY_DOC_TYPES = frozenset({DocumentType.PROPERTY_DEED, DocumentType.RENTAL_AGREEMENT})

#: Роли «чистого» жителя (реэкспорт — `residents.core.PURE_APPLICANT_ROLES`).
PURE_APPLICANT_ROLES = frozenset({"applicant", "resource_meter_entry"})

REFUSAL_PROPERTY_DOCUMENT = "property_document_required"
REFUSAL_PHONE = "phone_required"
REFUSAL_VERIFICATION = "verification_required"


def verification_refusal(*, has_property_doc: bool, in_person: bool = False) -> str | None:
    """Код отказа подтвердить верификацию или None."""
    if has_property_doc or in_person:
        return None
    return REFUSAL_PROPERTY_DOCUMENT


def is_pure_applicant(user) -> bool:
    """Только роли жителя. Пустые/NULL roles — тоже житель (соглашение кода:
    `db_roles or ["applicant"]`); иначе такой аккаунт обходил бы правило."""
    roles = set(parse_roles_safe(getattr(user, "roles", None)))
    return not roles - PURE_APPLICANT_ROLES


def account_refusal(user) -> str | None:
    """Код отказа дать жителю доступ (`approved`) или None.

    Стафф правилом не затрагивается: его активирует свой раздел.
    """
    if not is_pure_applicant(user):
        return None
    if not user.phone:
        return REFUSAL_PHONE
    if user.verification_status != "verified":
        return REFUSAL_VERIFICATION
    return None
