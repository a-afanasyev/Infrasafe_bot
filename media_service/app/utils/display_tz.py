"""Метка времени в зоне показа развёртывания (ARCH-137 C1-bis).

Контейнер живёт по UTC, и naive `datetime.now()` ставил в подпись к медиа
время на 5 часов раньше местного. Зона приходит из env DISPLAY_TZ (compose,
несекретное); своего канона business_time у media нет — сервис изолирован,
ради двух строк общий модуль не тянем. Модуль намеренно без app-импортов:
тестируется без конфиг-цепочки сервиса.
"""
import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

_DEFAULT_TZ = "Asia/Tashkent"


def _display_zone() -> ZoneInfo:
    try:
        return ZoneInfo(os.getenv("DISPLAY_TZ", _DEFAULT_TZ))
    except Exception:
        return ZoneInfo(_DEFAULT_TZ)


def display_now_str(fmt: str = "%d.%m.%Y %H:%M") -> str:
    """Текущее время в DISPLAY_TZ. Невалидная зона деградирует в дефолт,
    а не роняет отправку медиа."""
    return datetime.now(timezone.utc).astimezone(_display_zone()).strftime(fmt)


def display_instant_str(dt: datetime, fmt: str = "%d.%m.%Y %H:%M") -> str:
    """Хранимый инстант → строка в DISPLAY_TZ. naive трактуется как UTC —
    то же правило, что в боте (business_time): БД хранит UTC."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(_display_zone()).strftime(fmt)
