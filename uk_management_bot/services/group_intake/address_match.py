"""Поиск адреса по СПРАВОЧНИКУ (двор/дом) по свободному тексту.

Общий для staff-приёмки Group Intake и колл-центра (решение владельца
2026-11-07: менеджер вводит адрес со слов звонящего, ИИ вытаскивает подсказку,
этот матчер предлагает дворы/дома справочника, человек подтверждает).
Перенесён из handlers/group_intake.py без изменения логики; варианты дома
дополнительно несут ``yard_id`` — каскад выбора адреса в дашборде.
"""
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import contains_eager

from uk_management_bot.database.models.building import Building
from uk_management_bot.database.models.yard import Yard
from uk_management_bot.services.group_intake.translit import CYR_TO_LAT
from uk_management_bot.services.request_address import (
    format_building_address,
    format_yard_address,
)
from uk_management_bot.utils.sql_search import ci_contains, escape_like, is_postgres

# Кандидатов адреса в выборе — не больше, чем влезает кнопками.
_STAFF_MATCH_LIMIT = 4
# Капы матчера (security-review 2026-08-22): без них сообщение, набитое
# digit-токенами («потоп 1a 2b 3c …»), порождало до сотен последовательных
# SELECT'ов с ICU-collation на одно сообщение — тихий DoS БД от инсайдера.
_MAX_MATCH_ATTEMPTS = 8
_MAX_TEXT_DIGIT_TOKENS = 5


# Кириллица → латиница для адресного хинта: справочник может быть латинским
# («Yangi Olmazor, 14V»), а сотрудник пишет кириллицей («14в», «Янги Олмазор»).
# Транслит детерминированный, НЕ полагаемся на LLM: address_hint извлекается
# дословно из сообщения. Таблица общая с keyword-проходом категорий —
# services/group_intake/translit.py.
_CYR_TO_LAT = CYR_TO_LAT


def _hint_variants(needle: str) -> list[str]:
    """Хинт + его транслит-вариант (если отличается). Кириллический «14в»
    обязан находить латинский «14V» без участия человека."""
    variants = [needle]
    translit = needle.lower().translate(_CYR_TO_LAT)
    if translit != needle.lower():
        variants.append(translit)
    return variants


def _hint_needles(hint: str) -> list[str]:
    """Полный хинт + токены-запасные варианты (живой smoke: LLM отдал
    «у дома 14в», и подстрочный поиск целиком не нашёл «Yangi Olmazor, 14V»).

    Порядок: сначала весь хинт, затем токены с цифрой (номер дома — самый
    селективный признак), затем прочие слова по убыванию длины. Матчер идёт
    по списку до первого непустого результата, так что мусорные слова
    («дома», «подъезд») в дело вступают, только если ничего лучше нет.
    """
    import re

    needle = hint.strip()
    tokens = [t for t in re.split(r"\W+", needle, flags=re.UNICODE) if len(t) >= 2]
    tokens.sort(key=lambda t: (not any(ch.isdigit() for ch in t), -len(t)))
    seen = {needle.lower()}
    needles = [needle]
    for token in tokens:
        if token.lower() not in seen:
            seen.add(token.lower())
            needles.append(token)
    return needles


def _hint_predicate(column, needle: str, *, pg: bool):
    """OR по ci_contains для всех транслит-вариантов хинта."""
    from sqlalchemy import or_

    return or_(*(
        ci_contains(column, f"%{escape_like(variant)}%", is_postgres=pg)
        for variant in _hint_variants(needle)
    ))


def _digit_tokens(text: str) -> list[str]:
    """Токены с цифрой из произвольного текста (номер дома — «21v», «14в»),
    длиной ≥2, по убыванию длины. Чисто-числовые короткие («2 подъезд»)
    отсеиваются длиной, болтовня — требованием цифры."""
    import re

    tokens = [
        t for t in re.split(r"\W+", text, flags=re.UNICODE)
        if len(t) >= 2 and any(ch.isdigit() for ch in t)
    ]
    seen: set[str] = set()
    unique = []
    for token in sorted(tokens, key=len, reverse=True):
        if token.lower() not in seen:
            seen.add(token.lower())
            unique.append(token)
    return unique[:_MAX_TEXT_DIGIT_TOKENS]


def _match_staff_address_sync(db, scope: str, hint: Optional[str],
                              text: Optional[str] = None) -> list[dict]:
    """Адрес staff-репорта — по СПРАВОЧНИКУ, не по квартирам автора.

    scope=yard → поиск по дворам; building|apartment|unknown → по домам
    (сотрудник не заводит заявку в чужую квартиру — apartment трактуем как
    building). Поиск через ci_contains (единственный кириллице-безопасный
    путь при C-локали БД) по уже экранированному шаблону (escape_like);
    кириллица дополнительно пробуется в транслите (_hint_variants).

    Три эшелона, до первого непустого результата:
    1) полный LLM-хинт; 2) его токены (_hint_needles, цифра — приоритет);
    3) токены с цифрой из ПОЛНОГО текста сообщения — живой smoke показал,
       что LLM может выбросить номер дома из хинта («dom 2 podyezd» при
       «21v dom 2 podyezd…»), а в тексте номер есть всегда, если автор
       его назвал. Без хинта и без совпадений — пусто («укажите дом»).
    """
    pg = is_postgres(db)
    tried: set[str] = set()
    needles: list[str] = []
    hint_needle = (hint or "").strip()
    if hint_needle:
        needles.extend(_hint_needles(hint_needle))
    for token in _digit_tokens(text or ""):
        needles.append(token)
    for candidate_needle in needles:
        if len(tried) >= _MAX_MATCH_ATTEMPTS:
            break
        if candidate_needle.lower() in tried:
            continue
        tried.add(candidate_needle.lower())
        options = _query_staff_addresses(db, scope, candidate_needle, pg)
        if options:
            return options
    return []


def _query_staff_addresses(db, scope: str, needle: str, pg: bool) -> list[dict]:
    if scope == "yard":
        rows = db.execute(
            select(Yard)
            .where(
                Yard.is_active.is_(True),
                _hint_predicate(Yard.name, needle, pg=pg),
            )
            .order_by(Yard.name)
            .limit(_STAFF_MATCH_LIMIT)
        ).scalars().all()
        return [
            {
                "type": "yard",
                "id": yard.id,
                "label_public": format_yard_address(yard),
                "label_full": format_yard_address(yard),
            }
            for yard in rows
        ]
    rows = db.execute(
        select(Building)
        .join(Building.yard)
        .options(contains_eager(Building.yard))
        .where(
            Building.is_active.is_(True),
            Yard.is_active.is_(True),
            _hint_predicate(Building.address, needle, pg=pg),
        )
        .order_by(Building.address)
        .limit(_STAFF_MATCH_LIMIT)
    ).scalars().all()
    return [
        {
            "type": "building",
            "id": building.id,
            "label_public": format_building_address(building),
            "label_full": format_building_address(building),
            "yard_id": building.yard_id,
        }
        for building in rows
    ]
