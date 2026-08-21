"""Префильтр Group Intake: дешёвый отсев до LLM (чистая функция)."""
import pytest

from uk_management_bot.services.group_intake.prefilter import prefilter


@pytest.mark.parametrize(
    "text, has_photo, expected",
    [
        # Жёсткий инвариант: <10 символов — False ВСЕГДА, даже со словарным маркером.
        ("лифт", False, False),
        ("течёт", True, False),
        ("", False, False),
        ("   \n  ", True, False),
        # Команды и голые ссылки.
        ("/start@somebot и ещё текст", False, False),
        ("https://example.com/something", False, False),
        ("t.me/channel/123", False, False),
        # Словарные маркеры ru.
        ("не работает лифт", False, True),
        ("течёт стояк в подъезде", False, True),
        ("прорвало канализацию!!", False, True),
        ("нет света на этаже", False, True),
        # Словарные маркеры uz (latin).
        ("lift ishlamayapti", False, True),
        ("suv oqyapti podvalda", False, True),
        ("kanalizatsiya buzildi", False, True),
        # Длинный текст без маркеров — пропуск по длине.
        ("вчера видел во дворе что-то очень странное и непонятное", False, True),
        # Короткий (10..24) без маркеров и без фото — отсев.
        ("привет всем тут", False, False),
        # Тот же короткий, но с фото (caption >= 10) — пропуск.
        ("привет всем тут", True, True),
    ],
)
def test_prefilter_table(text, has_photo, expected):
    assert prefilter(text, has_photo) is expected
