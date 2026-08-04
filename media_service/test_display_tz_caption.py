"""ARCH-137 C1-bis: метка времени в подписи к медиа — в зоне показа.

Контейнер живёт по UTC, и до правки naive `datetime.now()` ставил в подпись
Telegram-сообщения время на 5 часов раньше местного — у каждого получателя.
Зона приходит из env DISPLAY_TZ (compose); мусорное значение обязано
деградировать в дефолт, а не ронять отправку медиа.
"""
from datetime import datetime

from app.utils.display_tz import display_now_str

FMT = "%d.%m.%Y %H:%M"


def test_display_tz_env_is_honored(monkeypatch):
    monkeypatch.setenv("DISPLAY_TZ", "UTC")
    utc_str = display_now_str()
    monkeypatch.setenv("DISPLAY_TZ", "Asia/Tashkent")
    tash_str = display_now_str()

    delta = datetime.strptime(tash_str, FMT) - datetime.strptime(utc_str, FMT)
    minutes = delta.total_seconds() / 60
    # Ташкент = UTC+5 без DST; минута люфта на границу минуты между вызовами
    assert 299 <= minutes <= 301, f"ожидал +5ч, получил {minutes} мин"


def test_default_is_tashkent(monkeypatch):
    monkeypatch.delenv("DISPLAY_TZ", raising=False)
    default_str = display_now_str()
    monkeypatch.setenv("DISPLAY_TZ", "Asia/Tashkent")
    tash_str = display_now_str()
    delta = abs((datetime.strptime(tash_str, FMT) - datetime.strptime(default_str, FMT)).total_seconds())
    assert delta <= 60


def test_garbage_zone_falls_back_not_raises(monkeypatch):
    monkeypatch.setenv("DISPLAY_TZ", "Not/AZone")
    s = display_now_str()  # не должно бросить
    datetime.strptime(s, FMT)  # и формат подписи сохранён
