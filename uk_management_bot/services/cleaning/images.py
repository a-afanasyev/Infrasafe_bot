"""Безопасное декодирование фото уборки, отпечатки и штамп.

``validate_completion_photo`` проверяет только размер и сигнатуру; сюда приходят
уже прошедшие её байты. Здесь — полноценное декодирование с лимитом пикселей и
перекодировка в JPEG (метаданные и «довески» отбрасываются). Отпечатки считаются
по пикселям БЕЗ штампа: штамп меняется от загрузки к загрузке.

Функции синхронные и тяжёлые — вызывать через ``asyncio.to_thread``.
"""
from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass

from PIL import Image, ImageDraw, UnidentifiedImageError

MAX_PIXELS = 16_000_000   # выше — отказ: защита от «бомб» распаковки (клиент шлёт кадр до 1600 px)
MAX_SIDE = 1600           # как в клиентском downscaleImage.ts
JPEG_QUALITY = 85
_DHASH_SIZE = 8


class BadImage(ValueError):
    """Байты не являются изображением, которое можно безопасно декодировать."""


@dataclass(frozen=True)
class Decoded:
    jpeg: bytes         # перекодированный кадр без штампа
    pixel_sha256: str   # точное совпадение пикселей
    dhash: str          # 64-битный перцептивный отпечаток, hex


def _dhash(img: Image.Image) -> str:
    gray = img.convert("L").resize((_DHASH_SIZE + 1, _DHASH_SIZE), Image.Resampling.LANCZOS)
    px = gray.tobytes()
    bits = 0
    for row in range(_DHASH_SIZE):
        base = row * (_DHASH_SIZE + 1)
        for col in range(_DHASH_SIZE):
            bits = (bits << 1) | (px[base + col] > px[base + col + 1])
    return f"{bits:016x}"


def decode(photo_bytes: bytes) -> Decoded:
    """Проверить и нормализовать кадр; ``BadImage`` — если это не картинка."""
    try:
        with Image.open(io.BytesIO(photo_bytes)) as probe:
            if probe.width * probe.height > MAX_PIXELS:
                raise BadImage("too_many_pixels")
            probe.verify()
        with Image.open(io.BytesIO(photo_bytes)) as src:  # verify() делает объект непригодным
            img = src.convert("RGB")
    except BadImage:
        raise
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, SyntaxError, ValueError) as exc:
        raise BadImage(type(exc).__name__) from None
    img.thumbnail((MAX_SIDE, MAX_SIDE), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=JPEG_QUALITY)
    return Decoded(jpeg=out.getvalue(), pixel_sha256=hashlib.sha256(img.tobytes()).hexdigest(), dhash=_dhash(img))


def stamp(jpeg: bytes, text: str) -> bytes:
    """Нанести серверный штамп в нижнюю полосу кадра.

    # ponytail: встроенный шрифт Pillow без кириллицы, поэтому штамп — ASCII
    # (дата, время, № задания, точка, уровень доверия). Адрес текстом — когда
    # в образ положим TTF с кириллицей.
    """
    with Image.open(io.BytesIO(jpeg)) as src:
        img = src.convert("RGB")
    draw = ImageDraw.Draw(img)
    band = max(18, img.height // 16)
    draw.rectangle((0, img.height - band, img.width, img.height), fill=(0, 0, 0))
    draw.text((6, img.height - band + band // 4), text, fill=(255, 255, 255))
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=JPEG_QUALITY)
    return out.getvalue()
