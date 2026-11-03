"""Владельцы лицевых счетов (выгрузка Mening Uyim) по квартирам.

Выгрузка — CSV ``Лицевой счёт;ФИО`` со значениями в кавычках. Каждая загрузка
заменяет таблицу ``account_owners`` целиком (снимок). Квартира связана со
счётом через ``apartments.account_number``; ФИО владельца — только информация
менеджеру, правила допуска (`services/residents/approval_rules.py`) её не видят.
"""
from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from typing import Iterable, Literal

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.database.models import AccountOwner, Apartment, AuditLog
from uk_management_bot.services.addresses.core import (
    _ACCOUNT_NUMBER_MAX_LEN,
    _ACCOUNT_NUMBER_RE,
)
from uk_management_bot.utils.person_name import normalize_full_name

MAX_BYTES = 5 * 1024 * 1024
MAX_ROWS = 20_000

_ACCOUNT_HEADERS = {"лицевой счёт", "лицевой счет", "л/с", "лс", "hisob raqami", "account"}
_NAME_HEADERS = {"фио", "ф.и.о.", "ф.и.о", "f.i.sh", "f.i.sh.", "fish", "egasi", "владелец"}

OwnerCheckStatus = Literal["found", "no_account", "not_in_list"]


class OwnersFileError(ValueError):
    """Файл не похож на выгрузку владельцев — показывается менеджеру как есть."""


@dataclass(frozen=True)
class ImportSummary:
    total: int
    skipped: int
    linked: int


@dataclass(frozen=True)
class OwnerCheck:
    status: OwnerCheckStatus
    account_number: str | None = None
    owner_name: str | None = None


def _decode(raw: bytes) -> str:
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        # Excel на Windows сохраняет CSV в cp1251.
        return raw.decode("cp1251")


def parse_owners_csv(raw: bytes) -> tuple[dict[str, str], int]:
    """CSV → ({счёт: ФИО}, число пропущенных строк). Дубль счёта — последний."""
    if len(raw) > MAX_BYTES:
        raise OwnersFileError("Файл больше 5 МБ")
    text = _decode(raw)
    delimiter = ";" if text.count(";") >= text.count(",") else ","
    rows = csv.reader(io.StringIO(text), delimiter=delimiter)
    header = [cell.strip().lower() for cell in next(rows, [])]
    try:
        acc_col = next(i for i, h in enumerate(header) if h in _ACCOUNT_HEADERS)
        name_col = next(i for i, h in enumerate(header) if h in _NAME_HEADERS)
    except StopIteration:
        raise OwnersFileError("Нужны колонки «Лицевой счёт» и «ФИО»") from None

    owners: dict[str, str] = {}
    skipped = 0
    for count, row in enumerate(rows, start=1):
        if count > MAX_ROWS:
            raise OwnersFileError(f"Больше {MAX_ROWS} строк")
        if not any(cell.strip() for cell in row):
            continue
        account = row[acc_col].strip() if len(row) > acc_col else ""
        name = normalize_full_name(row[name_col]) if len(row) > name_col else ""
        if (not name or len(account) > _ACCOUNT_NUMBER_MAX_LEN
                or not _ACCOUNT_NUMBER_RE.fullmatch(account)):
            skipped += 1
            continue
        owners[account] = name[:255]
    if not owners:
        raise OwnersFileError("В файле нет ни одной строки с лицевым счётом и ФИО")
    return owners, skipped


async def replace_owners(
    db: AsyncSession, owners: dict[str, str], skipped: int, actor_id: int,
) -> ImportSummary:
    """Заменить снимок владельцев одной транзакцией."""
    await db.execute(delete(AccountOwner))
    db.add_all(
        AccountOwner(account_number=acc, owner_name=name, imported_by=actor_id)
        for acc, name in owners.items()
    )
    linked = await _count_linked(db, owners.keys())
    # ФИО в аудит не пишем — только объём.
    db.add(AuditLog(
        action="account_owners_imported",
        user_id=actor_id,
        details=json.dumps({"total": len(owners), "skipped": skipped, "linked": linked}),
    ))
    await db.commit()
    return ImportSummary(total=len(owners), skipped=skipped, linked=linked)


async def _count_linked(db: AsyncSession, accounts: Iterable[str]) -> int:
    accounts = list(accounts)
    linked = 0
    # IN-список кусками: на 20 000 счетов не упираемся в лимит параметров.
    for start in range(0, len(accounts), 1000):
        chunk = accounts[start:start + 1000]
        linked += (await db.execute(
            select(func.count()).select_from(Apartment).where(Apartment.account_number.in_(chunk))
        )).scalar_one()
    return linked


async def owners_summary(db: AsyncSession) -> dict:
    """Сколько владельцев загружено, когда, и сколько из них нашли свою квартиру."""
    total, imported_at = (await db.execute(
        select(func.count(), func.max(AccountOwner.imported_at))
    )).one()
    linked = (await db.execute(
        select(func.count()).select_from(AccountOwner)
        .join(Apartment, Apartment.account_number == AccountOwner.account_number)
    )).scalar_one()
    return {"total": total, "linked": linked, "imported_at": imported_at}


async def owner_lookup(
    db: AsyncSession, apartment_ids: Iterable[int],
) -> dict[int, tuple[str | None, str | None]]:
    """{apartment_id: (account_number, owner_name)} одним запросом."""
    ids = set(apartment_ids)
    if not ids:
        return {}
    rows = await db.execute(
        select(Apartment.id, Apartment.account_number, AccountOwner.owner_name)
        .outerjoin(AccountOwner, AccountOwner.account_number == Apartment.account_number)
        .where(Apartment.id.in_(ids))
    )
    return {apt_id: (account, owner) for apt_id, account, owner in rows.all()}


def owner_check(found: tuple[str | None, str | None] | None) -> OwnerCheck:
    """Кто владелец лицевого счёта квартиры по Mening Uyim."""
    account, owner = found or (None, None)
    if not account:
        return OwnerCheck(status="no_account")
    if not owner:
        return OwnerCheck(status="not_in_list", account_number=account)
    return OwnerCheck(status="found", account_number=account, owner_name=owner)
