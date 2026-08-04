"""ARCH-137 B3: префикс номера заявки отвязан от зоны показа.

Номер — идентификатор: его дневной префикс YYMMDD обязан считаться в одной и
той же зоне всю жизнь системы, независимо от настраиваемой DISPLAY_TZ. До
правки `_params()` вызывал `business_today()` — то есть после перевода
`BUSINESS_TZ` на `settings.DISPLAY_TZ` префикс молча поехал бы за конфигом.
"""

from datetime import date, timedelta

from uk_management_bot.services import request_number_service as rns
from uk_management_bot.utils.datetime_utils import utc_now


def test_prefix_ignores_business_today(monkeypatch):
    """Сентинел вместо business_today: генератор не должен его звать вообще."""
    sentinel = date(1999, 1, 1)
    monkeypatch.setattr(rns, "business_today", lambda: sentinel)

    before = utc_now().astimezone(rns.REQUEST_NUMBER_TZ).date()
    prefix, params = rns.RequestNumberService._params(None)
    after = utc_now().astimezone(rns.REQUEST_NUMBER_TZ).date()

    assert prefix != sentinel.strftime("%y%m%d"), "префикс посчитан через business_today"
    # окно на случай гонки с местной полуночью между двумя замерами
    assert prefix in {before.strftime("%y%m%d"), after.strftime("%y%m%d")}
    assert params["pattern"] == f"{prefix}-%"


def test_request_number_tz_is_pinned_tashkent():
    """Константа идентификатора: НЕ равняется на display-канон, а прибита."""
    assert str(rns.REQUEST_NUMBER_TZ) == "Asia/Tashkent"


def test_explicit_creation_date_still_wins(monkeypatch):
    d = date(2026, 1, 15)
    prefix, _ = rns.RequestNumberService._params(d)
    assert prefix == "260115"


def test_prefix_is_tashkent_not_utc_after_evening():
    """Контроль смысла: инстант 20:00Z = следующий день по Ташкенту (+5)."""
    evening_utc = utc_now().replace(hour=20, minute=0)
    local = evening_utc.astimezone(rns.REQUEST_NUMBER_TZ).date()
    assert local == (evening_utc.date() + timedelta(days=1))
