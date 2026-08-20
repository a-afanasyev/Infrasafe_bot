"""Канон ФИО: нормализация, валидация, раскладка по двум колонкам.

Пинится и обратимость: `split_full_name` → склейка `utils/user_names.full_name`
обязана вернуть ровно нормализованную строку, иначе менеджер увидит не то, что
ввёл.
"""
import pytest

from uk_management_bot.utils.person_name import (
    MAX_FULL_NAME_LEN,
    InvalidFullName,
    normalize_full_name,
    split_full_name,
    validate_full_name,
)
from uk_management_bot.utils.user_names import full_name as render_full_name


class _U:
    def __init__(self, first, last):
        self.first_name = first
        self.last_name = last


class TestNormalize:
    def test_collapses_inner_whitespace_and_strips(self):
        assert normalize_full_name("  Иванов   Иван  ") == "Иванов Иван"

    def test_newlines_and_tabs_become_single_space(self):
        assert normalize_full_name("Иванов\n\tИван") == "Иванов Иван"

    def test_drops_zero_width_and_bidi_controls(self):
        # U+200B ZWSP и U+202E RLO — невидимые; в подписи кнопки и в тексте
        # уведомления они дают имя, которое глазами не отличить от чужого.
        assert normalize_full_name("Ива​нов‮ Иван") == "Иванов Иван"

    def test_non_string_is_empty(self):
        assert normalize_full_name(None) == ""


class TestValidate:
    def test_returns_normalized_value(self):
        assert validate_full_name("  Пётр   Петров ") == "Пётр Петров"

    def test_empty_rejected(self):
        with pytest.raises(InvalidFullName) as e:
            validate_full_name("   ")
        assert e.value.code == "empty"

    def test_invisible_only_rejected_as_empty(self):
        with pytest.raises(InvalidFullName) as e:
            validate_full_name("​​")
        assert e.value.code == "empty"

    def test_without_letters_rejected(self):
        # «123» / «---» — не опечатка, а мусор: пропустив его, мы получим
        # карточку без опознаваемого человека.
        with pytest.raises(InvalidFullName) as e:
            validate_full_name("12345")
        assert e.value.code == "no_letters"

    def test_too_long_rejected(self):
        with pytest.raises(InvalidFullName) as e:
            validate_full_name("Я" * (MAX_FULL_NAME_LEN + 1))
        assert e.value.code == "too_long"

    def test_at_limit_accepted(self):
        value = "Я" * MAX_FULL_NAME_LEN
        assert validate_full_name(value) == value

    def test_limit_fits_db_column(self):
        # users.first_name/last_name — String(255); одно слово целиком уходит
        # в first_name, поэтому лимит обязан быть меньше 255.
        assert MAX_FULL_NAME_LEN < 255


class TestSplit:
    def test_single_word_leaves_last_name_empty(self):
        assert split_full_name("Иванов") == ("Иванов", None)

    def test_two_words(self):
        assert split_full_name("Иванов Иван") == ("Иванов", "Иван")

    def test_three_words_tail_goes_to_last_name(self):
        # Канон регистрации (api/registration/router.py): первое слово →
        # first_name, ВЕСЬ остаток → last_name.
        assert split_full_name("Иванов Иван Иванович") == ("Иванов", "Иван Иванович")

    @pytest.mark.parametrize(
        "value",
        ["Иванов", "Иванов Иван", "Иванов Иван Иванович", "Ким Ён", "O'Brien Patrick"],
    )
    def test_split_then_render_is_identity(self, value):
        first, last = split_full_name(value)
        assert render_full_name(_U(first, last)) == value
