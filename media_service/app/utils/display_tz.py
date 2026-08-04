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


def display_now_str(fmt: str = "%d.%m.%Y %H:%M") -> str:
    """Текущее время в DISPLAY_TZ. Невалидная зона деградирует в дефолт,
    а не роняет отправку медиа."""
    try:
        tz = ZoneInfo(os.getenv("DISPLAY_TZ", _DEFAULT_TZ))
    except Exception:
        tz = ZoneInfo(_DEFAULT_TZ)
    return datetime.now(timezone.utc).astimezone(tz).strftime(fmt)
