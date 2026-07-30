"""Адресные хелперы публичной витрины: `derive_public_address` (pure, без I/O)
и fail-closed эвристика `address_looks_like_apartment`."""

import re
from typing import Optional

from uk_management_bot.database.models.request import Request
from uk_management_bot.services.request_address import (
    format_building_address,
    format_yard_address,
)

# ===========================================================================
# derive_public_address — pure, без I/O
# ===========================================================================


def derive_public_address(request: Request) -> Optional[str]:
    """Анонимизированный адрес для публичной витрины.

    НИКОГДА не копия `Request.address` (та хранит ", кв. N" для квартир).
    Заявки уровня дом/двор используют собственный канонический форматтер;
    заявки уровня квартира намеренно пере-выводятся из РОДИТЕЛЬСКОГО ДОМА
    (`format_building_address`, а не `format_apartment_address`, который
    включил бы номер квартиры). legacy/NULL address_type всегда даёт None
    (ручные work-report'ы для них требуют явного building_id/yard_id
    override — забота будущей задачи).

    Вызывающий обязан заранее (eager) загрузить `request.building_obj.yard`,
    `request.apartment_obj.building.yard`, `request.yard_obj` — эта функция
    никогда не должна триггерить lazy-load (async SQLAlchemy на нём падает).
    """
    if request.address_type == "building" and request.building_obj is not None:
        return format_building_address(request.building_obj)
    if (
        request.address_type == "apartment"
        and request.apartment_obj is not None
        and request.apartment_obj.building is not None
    ):
        return format_building_address(request.apartment_obj.building)
    if request.address_type == "yard" and request.yard_obj is not None:
        return format_yard_address(request.yard_obj)
    return None


_APARTMENT_MARKER_PATTERN = re.compile(r"кв\.?\s*\d", re.IGNORECASE)


def address_looks_like_apartment(address: str) -> bool:
    """Fail-closed heuristic: True if the string contains an apartment-number
    marker (e.g. "кв. 42", "кв42", "Кв. 7"). This is a REJECT guard, not a
    cleaner — legacy free-text address data spans years of manual entry and a
    regex "fix-up" risks a false negative that publishes an apartment number
    irreversibly; false positives (rejecting something safe) are the
    acceptable failure mode here, not false negatives."""
    return bool(_APARTMENT_MARKER_PATTERN.search(address))
