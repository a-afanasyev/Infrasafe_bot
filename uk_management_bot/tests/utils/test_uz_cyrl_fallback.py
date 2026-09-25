"""Язык профиля uz_cyrl (узбекская кириллица) и цепочка фолбэка переводов.

Своего файла у кириллицы нет: локаль строится транслитерацией uz.json
(``utils/uz_translit``, Фаза 3). Цепочка ключа uz_cyrl → uz → ru — ключ,
которого нет в uz, отдаётся по-русски (русский не транслитерируется).
"""
import os

import pytest

from uk_management_bot.utils import helpers
from uk_management_bot.utils.helpers import _locale_cache, get_text, load_locale


def test_no_hand_maintained_uz_cyrl_locale_file():
    # Ручной uz_cyrl.json разъехался бы с uz.json — кириллица только производная.
    assert not os.path.exists(os.path.join(helpers._resolve_locales_dir(), "uz_cyrl.json"))


def test_missing_uz_cyrl_file_builds_cyrillic_from_uz():
    from uk_management_bot.utils.uz_translit import to_cyrillic

    _locale_cache.pop("uz_cyrl", None)
    uz = get_text("buttons.cancel", language="uz")
    ru = get_text("buttons.cancel", language="ru")
    assert uz != ru  # иначе тест не различает uz и ru
    assert get_text("buttons.cancel", language="uz_cyrl") == to_cyrillic(uz)
    assert set(load_locale("uz_cyrl")) == set(load_locale("uz"))


def test_chain_prefers_uz_cyrl_then_uz_then_ru(monkeypatch):
    monkeypatch.setitem(_locale_cache, "uz_cyrl", {"k": {"cyrl": "Кирилл"}})
    monkeypatch.setitem(_locale_cache, "uz", {"k": {"cyrl": "Lotin", "latin": "Lotin"}})
    monkeypatch.setitem(_locale_cache, "ru", {"k": {"cyrl": "Рус", "latin": "Рус", "ru_only": "Рус"}})

    assert get_text("k.cyrl", language="uz_cyrl") == "Кирилл"
    assert get_text("k.latin", language="uz_cyrl") == "Lotin"
    assert get_text("k.ru_only", language="uz_cyrl") == "Рус"
    assert get_text("k.absent", language="uz_cyrl") == "k.absent"


def test_uz_cyrl_uses_uzbek_plural_rules(monkeypatch):
    monkeypatch.setitem(_locale_cache, "uz_cyrl", {"n": "{count} та", "n_plural": "{count} тадан"})
    # Узбекское правило: 5 → _plural (русское дало бы _plural_many и откат на базовый ключ).
    assert get_text("n", language="uz_cyrl", count=5) == "5 тадан"
    assert get_text("n", language="uz_cyrl", count=1) == "1 та"


def test_uz_cyrl_is_a_supported_profile_language():
    from uk_management_bot.utils.language_helpers import SUPPORTED_LANGUAGES

    assert "uz_cyrl" in SUPPORTED_LANGUAGES


def test_button_texts_have_no_duplicates_from_fallback():
    from uk_management_bot.utils.button_texts import get_button_texts_for_all_languages

    texts = get_button_texts_for_all_languages("buttons.cancel")
    assert len(texts) == len(set(texts))
    assert get_text("buttons.cancel", language="uz") in texts


@pytest.mark.parametrize("language", ["ru", "uz", "uz_cyrl"])
def test_language_choice_keyboard_builds_for_every_profile_language(language):
    from uk_management_bot.keyboards.profile import get_language_choice_keyboard

    markup = get_language_choice_keyboard(language)
    callbacks = [b.callback_data for row in markup.inline_keyboard for b in row]
    # Выбор в боте — ru/uz; кириллица выбирается в Mini App (Фаза 2).
    assert callbacks == ["set_language_ru", "set_language_uz", "cancel_language_choice"]


def test_uz_cyrl_keyboard_marks_uzbek_as_selected():
    from uk_management_bot.keyboards.profile import get_language_choice_keyboard

    uz = get_language_choice_keyboard("uz")
    cyrl = get_language_choice_keyboard("uz_cyrl")
    from uk_management_bot.utils.uz_translit import to_cyrillic

    texts = lambda m: [b.text for row in m.inline_keyboard for b in row]  # noqa: E731
    # Те же кнопки (отмечен узбекский), только кириллицей.
    assert texts(cyrl) == [to_cyrillic(t) for t in texts(uz)]


def test_localization_middleware_takes_language_from_fresh_user_record():
    """Язык не кэшируется: middleware берёт users.language из пользователя,
    которого auth-middleware читает из БД на каждом апдейте, — смена языка
    менеджером действует со следующего сообщения без рестарта бота."""
    import asyncio
    from types import SimpleNamespace

    from uk_management_bot.middlewares.localization import localization_middleware

    async def handler(event, data):
        return data["language"]

    async def run(language):
        return await localization_middleware(handler, object(), {"user": SimpleNamespace(language=language)})

    assert asyncio.run(run("uz_cyrl")) == "uz_cyrl"
    assert asyncio.run(run("ru")) == "ru"
