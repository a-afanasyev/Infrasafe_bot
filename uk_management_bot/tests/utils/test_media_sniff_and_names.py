"""П5b — канон сниффера MIME и канон имени пользователя (AUD5-APIFE-13).

Сведение копий тут не механическое, и тесты фиксируют именно это:

* сниффер знает ВСЕ форматы системы, а что допустимо — решает вызывающий своим
  allowlist'ом (иначе библиотечный код завязан на политику эндпоинтов);
* `full_name` отвечает только «Имя Фамилия или None»; фолбэки у точек показа
  разные исторически, и канон их НЕ унифицирует, чтобы техническая правка не
  меняла видимые строки.
"""
import pytest

from uk_management_bot.utils.media_sniff import (
    IMAGE_MIME_TYPES,
    VIDEO_MIME_TYPES,
    sniff_media_mime,
)
from uk_management_bot.utils.user_names import display_name, full_name

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 16
GIF87 = b"GIF87a" + b"\x00" * 16
GIF89 = b"GIF89a" + b"\x00" * 16
MP4 = b"\x00\x00\x00\x18ftypisom" + b"\x00" * 8
MOV = b"\x00\x00\x00\x14ftypqt  " + b"\x00" * 8
WEBP = b"RIFF\x00\x00\x00\x00WEBP" + b"\x00" * 8
# HEIC — тоже ISO BMFF с боксом 'ftyp'; до BUG-132 попадал в ветку mp4.
HEIC = b"\x00\x00\x00\x18ftypheic" + b"\x00" * 8


class TestSniffer:
    @pytest.mark.parametrize("data,expected", [
        (JPEG, "image/jpeg"),
        (PNG, "image/png"),
        (GIF87, "image/gif"),
        (GIF89, "image/gif"),
        (MP4, "video/mp4"),
        (MOV, "video/mov"),
        (WEBP, "image/webp"),
        (HEIC, "image/heic"),
    ])
    def test_known_signatures(self, data, expected):
        assert sniff_media_mime(data) == expected

    @pytest.mark.parametrize("data", [
        b"",
        b"\xff\xd8",                      # обрезанная JPEG-сигнатура
        b"<svg xmlns='http://www.w3.org/2000/svg'></svg>",
        b"<!DOCTYPE html><html></html>",
        b"GIF88a" + b"\x00" * 16,         # похожая, но не та версия
        b"\x00\x00\x00\x18ftyp",          # 'ftyp' есть, но короче 12 байт
    ])
    def test_unknown_returns_none(self, data):
        """None означает «не наш формат» — вызывающий обязан отказать."""
        assert sniff_media_mime(data) is None

    def test_svg_is_not_mistaken_for_an_image(self):
        """Смысл сниффера: SVG/HTML не должны пролезать под видом image/*."""
        assert sniff_media_mime(b"<svg/>") not in IMAGE_MIME_TYPES

    def test_declared_sets_match_what_the_sniffer_returns(self):
        """Наборы-константы обязаны совпадать с реальным выводом функции.

        Иначе вызывающий отфильтрует по устаревшему множеству и молча отвергнет
        формат, который сниффер уже умеет.
        """
        produced = {
            sniff_media_mime(d)
            for d in (JPEG, PNG, GIF87, MP4, MOV, WEBP, HEIC)
        }
        assert produced == IMAGE_MIME_TYPES | VIDEO_MIME_TYPES


class _U:
    def __init__(self, first=None, last=None):
        self.first_name = first
        self.last_name = last


class TestFullName:
    @pytest.mark.parametrize("user,expected", [
        (_U("Иван", "Петров"), "Иван Петров"),
        (_U("Иван", None), "Иван"),
        (_U(None, "Петров"), "Петров"),
        (_U(None, None), None),
        (_U("", ""), None),
        (None, None),
    ])
    def test_variants(self, user, expected):
        assert full_name(user) == expected

    def test_no_stray_whitespace_when_one_part_missing(self):
        """Регрессия исходных копий: f-string давал ' Петров' с ведущим пробелом."""
        assert full_name(_U(None, "Петров")) == "Петров"

    def test_object_without_name_attributes_does_not_crash(self):
        """Канон вызывается и на объектах не-User (например, из чужих сервисов)."""
        assert full_name(object()) is None


class _UD:
    """Пользователь с полным набором полей, участвующих в фолбэке."""

    def __init__(self, first=None, last=None, username=None, telegram_id=None, id=7):
        self.first_name = first
        self.last_name = last
        self.username = username
        self.telegram_id = telegram_id
        self.id = id


class TestDisplayName:
    """REFACTOR-133: один фолбэк вместо пяти — `@username`, иначе `ID{telegram_id}`."""

    @pytest.mark.parametrize("user,expected", [
        (_UD("Иван", "Петров", "ivan", 555), "Иван Петров"),
        (_UD(None, None, "ivan", 555), "@ivan"),
        (_UD(None, None, None, 555), "ID555"),
        (_UD("", "", "", 555), "ID555"),
    ])
    def test_fallback_ladder(self, user, expected):
        assert display_name(user) == expected

    def test_telegram_id_is_preferred_over_internal_serial(self):
        """Выбор формата: по telegram_id человека находят, по serial'у — нет."""
        assert display_name(_UD(None, None, None, telegram_id=555, id=7)) == "ID555"

    def test_serial_only_when_there_is_nothing_else(self):
        assert display_name(_UD(None, None, None, None, id=7)) == "#7"

    def test_result_is_never_empty_for_a_real_user(self):
        assert display_name(_UD()) not in (None, "")

    def test_absent_user_is_still_none(self):
        """None означает «пользователя нет», а не «имя не нашлось»."""
        assert display_name(None) is None

    def test_max_len_counts_the_ellipsis(self):
        """Предел — длина результата: подпись кнопки не должна вылезать за него."""
        long = _UD("Иннокентий", "Всеволодович-Раскольников", None, 555)

        shown = display_name(long, max_len=25)

        assert len(shown) == 25
        assert shown.endswith("...")

    def test_short_name_is_untouched_by_the_limit(self):
        assert display_name(_UD("Иван", "Петров", None, 555), max_len=25) == "Иван Петров"


def test_display_points_have_no_private_fallbacks():
    """AC пункта: собственных лестниц фолбэка в точках показа не осталось.

    Гейт нужен, потому что новый экран со списком людей пишется копипастой
    соседнего — так пять расхождений и появились. Проверяются те файлы, где
    фолбэк был; локализованные «неизвестный» (shift_transfer, handlers/
    user_verification) сюда не входят намеренно: это другой, переводимый ответ.
    """
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[3] / "uk_management_bot"
    watched = [
        "keyboards/user_verification.py",
        "keyboards/user_management.py",
        "keyboards/admin.py",
        "api/shifts/executor_router.py",
        "api/feedback/router.py",
    ]
    pattern = re.compile(r"""(f"@\{|f"ID\{|f"User \{|f"#\{|f"id\{)""")
    offenders = []
    for rel in watched:
        for i, line in enumerate(
            (root / rel).read_text(encoding="utf-8").splitlines(), start=1
        ):
            if pattern.search(line):
                offenders.append(f"{rel}:{i}")

    assert not offenders, (
        "снова собственный фолбэк имени вместо `display_name`: " + ", ".join(offenders)
    )
