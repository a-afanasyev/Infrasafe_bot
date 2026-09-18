"""AUD7-SIMP-01: в config/locales живут только читаемые loader'ом файлы.

`utils/helpers.load_locale` читает `<lang>.json` для ru/uz (с фолбэком на ru);
девять архивных/добавочных JSON (all_locales.json, *.backup*, *_new_keys.json,
ru_additional_keys.json — 26 419 строк / 1,84 MiB) никем не читались, но
копировались в образ (`Dockerfile: COPY uk_management_bot/`) и засоряли поиск.
Гейт: любой лишний файл в каталоге — красный тест, а не тихий рост образа.
"""
from pathlib import Path

from uk_management_bot.utils.helpers import load_locale

LOCALES_DIR = Path(__file__).resolve().parents[1] / "config" / "locales"
ALLOWED = {"ru.json", "uz.json"}


def test_locales_dir_contains_only_ru_and_uz():
    present = {p.name for p in LOCALES_DIR.iterdir() if p.is_file()}
    extra = sorted(present - ALLOWED)
    assert not extra, f"в config/locales лишние файлы (loader читает только ru/uz): {extra}"
    assert ALLOWED <= present


def test_loader_and_fallback_still_work():
    assert load_locale("ru").get("buttons"), "ru.json не загрузился"
    assert load_locale("uz").get("buttons"), "uz.json не загрузился"
    assert load_locale("xx") == load_locale("ru"), "фолбэк на ru сломан"
