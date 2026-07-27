"""Определение MIME по магическим байтам — единственная реализация (AUD5-APIFE-13).

Копий было две (`api/routes/media_proxy.py`, `api/feedback/router.py`), и они
уже разошлись: прокси знал видео (mp4/mov), обратная связь — только картинки.
Разошлись безобидно, но это ровно тот класс, где следующая правка (новый
формат, исправленная сигнатура) прилетает в одну копию из двух.

**Детекция и политика разделены сознательно.** Эта функция отвечает только на
вопрос «что это за байты», и знает все поддерживаемые системой типы. Что из
них ДОПУСТИМО в конкретной точке — решает вызывающий своим allowlist'ом:
прокси принимает и видео, обратная связь только изображения. Слить их в одну
функцию «сниффер с allowlist» нельзя, не завязав библиотечный код на политику
двух разных эндпоинтов.

Зачем вообще магические байты: media-service проверяет client-supplied
Content-Type, а не содержимое, поэтому подпись выводится на границе и дальше
передаётся уже server-derived тип — иначе HTML/SVG/JS можно было бы протащить
под видом image/* и получить обратно с подделанным типом.
"""

from __future__ import annotations

from typing import Optional

#: Изображения, которые система умеет распознавать.
IMAGE_MIME_TYPES = frozenset({"image/jpeg", "image/png", "image/gif"})
#: Видео. NB: HEIC не поддерживается ни здесь, ни в media-service.
VIDEO_MIME_TYPES = frozenset({"video/mp4", "video/mov"})


def sniff_media_mime(data: bytes) -> Optional[str]:
    """MIME по сигнатуре или None, если тип не распознан.

    None означает «не наш формат» — вызывающий обязан отказать, а не
    подставлять клиентский Content-Type.
    """
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    # ISO BMFF (mp4 / mov): бокс 'ftyp' в байтах 4..8, бренд в 8..12.
    if len(data) >= 12 and data[4:8] == b"ftyp":
        return "video/mov" if data[8:10] == b"qt" else "video/mp4"
    return None
