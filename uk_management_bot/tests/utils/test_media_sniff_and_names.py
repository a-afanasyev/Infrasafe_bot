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
from uk_management_bot.utils.user_names import full_name

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 16
GIF87 = b"GIF87a" + b"\x00" * 16
GIF89 = b"GIF89a" + b"\x00" * 16
MP4 = b"\x00\x00\x00\x18ftypisom" + b"\x00" * 8
MOV = b"\x00\x00\x00\x14ftypqt  " + b"\x00" * 8


class TestSniffer:
    @pytest.mark.parametrize("data,expected", [
        (JPEG, "image/jpeg"),
        (PNG, "image/png"),
        (GIF87, "image/gif"),
        (GIF89, "image/gif"),
        (MP4, "video/mp4"),
        (MOV, "video/mov"),
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
        produced = {sniff_media_mime(d) for d in (JPEG, PNG, GIF87, MP4, MOV)}
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
