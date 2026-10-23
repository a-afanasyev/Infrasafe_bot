"""A10-SAT-01/02: бомба-картинка не декодируется; превью не переживает удаление."""
import asyncio
import io

from PIL import Image


def _png(w: int, h: int) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (10, 20, 30)).save(buf, format="PNG")
    return buf.getvalue()


def test_make_preview_rejects_oversized_source(monkeypatch):
    from app.core.config import settings
    from app.services import preview_cache

    monkeypatch.setattr(settings, "preview_max_source_pixels", 1_000_000)

    assert preview_cache.make_preview(_png(1600, 1200)) is None  # 1,92 Мпкс > потолка
    assert preview_cache.make_preview(_png(800, 600)) is not None


def test_remove_deletes_cached_preview_and_is_idempotent(tmp_path, monkeypatch):
    from app.core.config import settings
    from app.services import preview_cache

    monkeypatch.setattr(settings, "preview_cache_dir", str(tmp_path / "cache"))

    asyncio.run(preview_cache.put(1, "250101-001", b"jpeg-bytes"))
    assert preview_cache.get(1, "250101-001") == b"jpeg-bytes"

    asyncio.run(preview_cache.remove(1, "250101-001"))
    assert preview_cache.get(1, "250101-001") is None

    asyncio.run(preview_cache.remove(1, "250101-001"))  # отсутствие файла — не ошибка
