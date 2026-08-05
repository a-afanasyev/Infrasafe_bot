"""ARCH-116: единственный источник бизнес-таймзоны на слое ПОКАЗА.

БД остаётся UTC (`DateTime(timezone=True)`, `utc_now()` при записи) — решение
владельца. Конвертация живёт ровно на границе «инстант → текст для человека» и
на обратной границе «бизнес-дата → окно для SQL-фильтра».

Зачем модуль, а не правка по месту: до него бизнес-tz существовала в репо
четырьмя независимыми копиями (номер заявки, окно авто-менеджера, фронт-дашборд,
учёт ресурсов), а показ смен в боте не использовал ни одну из них — исполнитель в
Ташкенте видел UTC, то есть время на 5 часов раньше своих часов, и смену,
начинающуюся после полуночи по местному, бот относил к предыдущему дню.

Два правила, которые здесь закреплены:

1. **naive трактуется как UTC.** sqlite не хранит tzinfo и отдаёт при чтении
   naive-значение (замерено), поэтому инстант из БД приезжает без зоны на
   тест-движке и с зоной на Postgres. Единая трактовка делает показ одинаковым;
   вариант «naive = локальное время процесса» дал бы разный результат на раннере
   и в контейнере.

2. **Окно дня — полуоткрытое `[lo, hi)` в UTC.** Так фильтр не зависит от
   `TimeZone`-GUC базы (`date(timestamptz)` считает дату в зоне сессии) и не
   мешает индексу по колонке, в отличие от `func.date(col) == d`. Правая граница
   строится от СЛЕДУЮЩЕЙ календарной даты, а не как `lo + 24ч` — тогда переход
   DST не сдвигает окно (у Ташкента DST нет, у формулы — есть).

Показ времени смен обязан идти через этот модуль: AST-гейт
`tests/services/test_business_tz_display.py` запрещает `.strftime(`,
`date.today()` и `func.date(` в файлах показа shift-домена.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Optional, Union
from zoneinfo import ZoneInfo

from uk_management_bot.config.settings import settings
from uk_management_bot.utils.datetime_utils import utc_now

# Бизнес-зона ПОКАЗА. Одна на развёртывание: settings.DISPLAY_TZ (дефолт
# Asia/Tashkent, ARCH-137 B2) — бот и фронт-дашборд называют одну дату одним
# днём. Номер заявки (YYMMDD) за ней НЕ следует: у него своя прибитая
# REQUEST_NUMBER_TZ (services/request_number_service.py) — префикс является
# частью идентификатора и менять зону после запуска нельзя.
BUSINESS_TZ = ZoneInfo(settings.DISPLAY_TZ)

# Значение, которое может быть как инстантом, так и уже календарной датой
# (у `date` конвертировать нечего — см. `_wall_value`).
DateOrDatetime = Union[datetime, date]


def to_business(dt: datetime) -> datetime:
    """Инстант → то же мгновение в бизнес-зоне. naive считается UTC."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(BUSINESS_TZ)


def business_date_of(dt: datetime) -> date:
    """Бизнес-дата инстанта (не UTC-дата)."""
    return to_business(dt).date()


def business_today(now: Optional[datetime] = None) -> date:
    """Сегодняшняя бизнес-дата. `now` инъецируется в тестах (freezegun в репо нет)."""
    return business_date_of(now if now is not None else utc_now())


def _wall_value(value: DateOrDatetime) -> DateOrDatetime:
    """Инстант конвертируем, `date` отдаём как есть.

    `datetime` — подкласс `date`, поэтому проверка порядком именно такая.
    """
    return to_business(value) if isinstance(value, datetime) else value


def fmt_time(dt: datetime) -> str:
    """`ЧЧ:ММ` по бизнес-зоне."""
    return to_business(dt).strftime("%H:%M")


def fmt_date(value: DateOrDatetime) -> str:
    """`ДД.ММ.ГГГГ` по бизнес-зоне (для `date` — как есть)."""
    return _wall_value(value).strftime("%d.%m.%Y")


def fmt_time_seconds(dt: datetime) -> str:
    """`ЧЧ:ММ:СС` по бизнес-зоне (метка «обновлено в …»)."""
    return to_business(dt).strftime("%H:%M:%S")


def fmt_datetime(dt: datetime) -> str:
    """`ДД.ММ.ГГГГ ЧЧ:ММ` по бизнес-зоне."""
    return to_business(dt).strftime("%d.%m.%Y %H:%M")


def fmt_day_month_time(dt: datetime) -> str:
    """`ДД.ММ ЧЧ:ММ` по бизнес-зоне (короткая подпись смены)."""
    return to_business(dt).strftime("%d.%m %H:%M")


def fmt_day_month(value: DateOrDatetime) -> str:
    """`ДД.ММ` по бизнес-зоне (для `date` — как есть)."""
    return _wall_value(value).strftime("%d.%m")


def business_day_window(day: date) -> tuple[datetime, datetime]:
    """Бизнес-день → полуоткрытое UTC-окно `[начало, начало следующего дня)`."""
    start = datetime.combine(day, time.min, tzinfo=BUSINESS_TZ)
    next_start = datetime.combine(day + timedelta(days=1), time.min, tzinfo=BUSINESS_TZ)
    return start.astimezone(timezone.utc), next_start.astimezone(timezone.utc)


def business_days_window(first: date, last: date) -> tuple[datetime, datetime]:
    """Диапазон бизнес-дней ВКЛЮЧИТЕЛЬНО → полуоткрытое UTC-окно."""
    return business_day_window(first)[0], business_day_window(last)[1]


def business_wall_clock(day: date, hour: int, minute: int = 0) -> datetime:
    """Стенка бизнес-зоны (день + чч:мм) → UTC-инстант.

    Для времени из шаблонов/настроек: «08:00» там означает 08:00 по зоне
    объекта, а не UTC (ARCH-135(б)).
    """
    wall = datetime.combine(day, time(hour=hour, minute=minute), tzinfo=BUSINESS_TZ)
    return wall.astimezone(timezone.utc)
