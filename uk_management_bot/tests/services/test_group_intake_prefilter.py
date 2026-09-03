"""Префильтр Group Intake: keyword-хит категории — пропускающий сигнал.

Без него три из шести эталонных прод-текстов резались ДО LLM: в `_MARKERS`
нет «poliv»/«elektrik», а длина меньше LONG_TEXT_LEN — заявка молча терялась.
"""

import pytest

from uk_management_bot.services.group_intake.prefilter import prefilter


@pytest.mark.parametrize("text", [
    "25v poliv yoqilsin",
    "20v 48kv elektrik kerak",
    "16v 106kv elektrik kerak",
])
def test_short_texts_with_category_keyword_pass(text):
    assert prefilter(text, has_photo=False) is True


def test_short_text_without_keyword_is_still_filtered():
    # 13 символов, ни маркера проблемы, ни ключевого слова категории
    assert prefilter("26v 2-podyezd", has_photo=False) is False


def test_marker_path_unchanged():
    assert prefilter("не работает лифт", has_photo=False) is True
    assert prefilter("/start", has_photo=False) is False
