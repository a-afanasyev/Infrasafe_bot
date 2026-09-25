"""Детектор «готово»-отчёта (Фаза 4): тег + слово «готово», кириллица/латиница."""
import pytest

from uk_management_bot.services.group_intake.done_detector import (
    has_done_word,
    is_done_report,
)


@pytest.mark.parametrize("text", [
    "готово",
    "Готово, подъезд 3",
    "СДЕЛАЛ",
    "сделала уборку",
    "сделано",
    "tayyor",
    "Tayyor 14V",
    "тайёр",
    "ТАЙЁР",
    "bajarildi",
    "бажарилди",
    "ish bajarildi.",
])
def test_done_words_positive(text):
    assert has_done_word(text)


@pytest.mark.parametrize("text", [
    "",
    None,
    "течёт кран в 3 подъезде",
    "не готово",
    "ещё не сделал",
    "tayyor emas",
    "приготовить раствор",  # «готов» не с начала слова
])
def test_done_words_negative(text):
    assert not has_done_word(text)


def test_report_requires_tag():
    assert is_done_report("сделал", has_tag=True)
    assert not is_done_report("сделал", has_tag=False)
    assert not is_done_report("течёт кран", has_tag=True)
