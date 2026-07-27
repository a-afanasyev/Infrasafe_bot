"""BUG-132 — таблицы сигнатур UK-границы и media-service не должны расходиться.

Копий сниффера три, и третья живёт в ДРУГОМ сервисе: `media_service` — отдельный
контейнер со своим деревом зависимостей, импортировать `uk_management_bot` он не
может, поэтому общий модуль здесь недоступен физически. Вместо него — контракт:
тест исполняет ОБЕ настоящие реализации на одном наборе байтов и требует
одинакового ответа.

Почему это не косметика. UK-граница выводит server-derived Content-Type и
передаёт его media-service вместо клиентского. Пока таблицы расходились:

* снимок с iPhone (HEIC — тоже ISO BMFF, тоже с боксом ``ftyp``) получал от UK
  тип ``video/mp4``, проходил allowlist media-service (mp4 в нём есть) и
  сохранялся как видео, которое не воспроизводится;
* ``.mov``, уже принятый UK как ``video/mov``, сниффер media не узнавал вовсе;
* webp media знал, а UK отвергал — то есть поддержка формата в media была
  недостижима через прокси.

Функция media вытаскивается из файла по AST и компилируется отдельно: она не
зависит ни от чего, кроме ``Optional``, а импорт пакета `app` потребовал бы
зависимостей чужого сервиса.
"""
from __future__ import annotations

import ast
from pathlib import Path
from typing import Optional

import pytest

from uk_management_bot.utils.media_sniff import (
    MEDIA_SERVICE_ACCEPTED_TYPES,
    sniff_media_mime,
)

ROOT = Path(__file__).resolve().parents[2]
MEDIA_ROUTER = ROOT / "media_service" / "app" / "api" / "v1" / "media.py"
MEDIA_CONFIG = ROOT / "media_service" / "app" / "core" / "config.py"


def _load_media_sniffer():
    """Скомпилировать `_sniff_image_mime` media-service без импорта его пакета."""
    tree = ast.parse(MEDIA_ROUTER.read_text(encoding="utf-8"))
    wanted = ("_sniff_image_mime", "_HEIF_BRANDS")
    body = [
        node
        for node in tree.body
        if (isinstance(node, ast.FunctionDef) and node.name in wanted)
        or (
            isinstance(node, ast.Assign)
            and any(
                isinstance(t, ast.Name) and t.id in wanted for t in node.targets
            )
        )
    ]
    assert any(
        isinstance(n, ast.FunctionDef) for n in body
    ), "в media_service больше нет `_sniff_image_mime` — контракт нужно переписать"
    namespace: dict = {"Optional": Optional}
    exec(compile(ast.Module(body=body, type_ignores=[]), str(MEDIA_ROUTER), "exec"), namespace)
    return namespace["_sniff_image_mime"]


def _media_allowed_types() -> set[str]:
    """Дефолт `allowed_file_types` из конфига media-service, тоже по AST."""
    tree = ast.parse(MEDIA_CONFIG.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign) and getattr(node.target, "id", "") == "allowed_file_types":
            return set(ast.literal_eval(node.value))
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "allowed_file_types" for t in node.targets
        ):
            return set(ast.literal_eval(node.value))
    raise AssertionError("`allowed_file_types` не найден в конфиге media-service")


media_sniff_mime = _load_media_sniffer()

_TAIL = b"\x00" * 8

#: По одному представителю каждой ветки таблицы + заведомо чужие байты.
CORPUS: dict[str, bytes] = {
    "jpeg": b"\xff\xd8\xff\xe0" + _TAIL,
    "png": b"\x89PNG\r\n\x1a\n" + _TAIL,
    "gif87": b"GIF87a" + _TAIL,
    "gif89": b"GIF89a" + _TAIL,
    "webp": b"RIFF\x00\x00\x00\x00WEBP" + _TAIL,
    "heic": b"\x00\x00\x00\x18ftypheic" + _TAIL,
    "heix": b"\x00\x00\x00\x18ftypheix" + _TAIL,
    "mif1": b"\x00\x00\x00\x18ftypmif1" + _TAIL,
    "msf1": b"\x00\x00\x00\x18ftypmsf1" + _TAIL,
    "mov": b"\x00\x00\x00\x14ftypqt  " + _TAIL,
    "mp4-isom": b"\x00\x00\x00\x18ftypisom" + _TAIL,
    "mp4-mp42": b"\x00\x00\x00\x18ftypmp42" + _TAIL,
    "mp4-avc1": b"\x00\x00\x00\x18ftypavc1" + _TAIL,
    "mp4-экзотика": b"\x00\x00\x00\x18ftypM4V " + _TAIL,
    "html": b"<html><body>hi</body></html>",
    "svg": b"<svg xmlns='http://www.w3.org/2000/svg'/>",
    "пусто": b"",
    "обрывок": b"\x00\x00\x00",
}


class TestBothSniffersAgree:
    @pytest.mark.parametrize("name", sorted(CORPUS))
    def test_same_bytes_give_same_type(self, name: str) -> None:
        data = CORPUS[name]
        uk = sniff_media_mime(data)
        media = media_sniff_mime(data)

        assert uk == media, (
            f"{name}: UK-граница говорит {uk!r}, media-service — {media!r}. "
            "Одни и те же байты обязаны получать один тип: UK передаёт свой "
            "вердикт дальше как server-derived Content-Type."
        )

    def test_iphone_photo_is_not_mistaken_for_video(self) -> None:
        """Регрессия BUG-132: HEIC — картинка, а не mp4.

        Отдельным тестом, потому что «обе стороны согласны» согласием на
        неверный ответ тоже удовлетворяется.
        """
        assert sniff_media_mime(CORPUS["heic"]) == "image/heic"

    def test_quicktime_is_recognised_by_both(self) -> None:
        assert sniff_media_mime(CORPUS["mov"]) == "video/mov"
        assert media_sniff_mime(CORPUS["mov"]) == "video/mov"


class TestDetectionIsWiderThanPolicy:
    """Распознаём больше, чем принимаем, — и это должно быть видно в коде."""

    def test_uk_mirror_of_media_allowlist_is_exact(self) -> None:
        assert MEDIA_SERVICE_ACCEPTED_TYPES == _media_allowed_types(), (
            "список принимаемых типов UK разошёлся с `allowed_file_types` "
            "media-service — файл будет принят на границе и отвергнут внутри"
        )

    @pytest.mark.parametrize("name", ["webp", "heic"])
    def test_recognised_but_not_accepted_types_are_refused_at_the_border(
        self, name: str
    ) -> None:
        """Формат распознан, но media его не хранит → отказ должен быть у нас."""
        sniffed = sniff_media_mime(CORPUS[name])

        assert sniffed is not None, "тип обязан распознаваться, иначе heic снова уедет как mp4"
        assert sniffed not in MEDIA_SERVICE_ACCEPTED_TYPES

    @pytest.mark.parametrize("name", ["html", "svg", "пусто", "обрывок"])
    def test_foreign_bytes_are_rejected_by_both(self, name: str) -> None:
        assert sniff_media_mime(CORPUS[name]) is None
        assert media_sniff_mime(CORPUS[name]) is None
