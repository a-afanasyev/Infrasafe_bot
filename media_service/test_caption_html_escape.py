"""AUD8-SEC-01: свободный текст в Telegram-подписях (parse_mode=HTML) экранируется.

Канон бота (BUG-174/178): любой пользовательский текст, попадающий в сообщение
с parse_mode="HTML", проходит html.escape. media-service строил подписи
f-строками без экранирования — description/ref/tags/archive_reason уходили в
канал менеджеров живой разметкой.
"""
from __future__ import annotations

import datetime as dt
import inspect
from types import SimpleNamespace

from app.services.media_storage import MediaStorageService


def _svc() -> MediaStorageService:
    # Конструктор поднимает Telegram-клиент и БД; подписи от состояния не зависят.
    return object.__new__(MediaStorageService)


def test_request_caption_escapes_description_and_tags() -> None:
    cap = _svc()._generate_caption(
        "260919-001",
        description='<a href="http://evil">жми</a> & <b>bold</b>',
        tags=["<i>tag</i>", "two words"],
    )
    assert "<a href" not in cap and "<b>" not in cap and "<i>" not in cap
    assert "&lt;a href=&quot;http://evil&quot;&gt;жми&lt;/a&gt; &amp; &lt;b&gt;bold&lt;/b&gt;" in cap
    assert "#&lt;i&gt;tag&lt;/i&gt;" in cap and "#two_words" in cap
    assert cap.startswith("📋 #260919-001")


def test_domain_caption_escapes_ref_description_tags() -> None:
    cap = _svc()._generate_domain_caption(
        ref="<u>ref</u>", description="a < b > c", tags=["x:y|z<"]
    )
    assert "<u>" not in cap and "a &lt; b &gt; c" in cap
    assert "🔑 &lt;u&gt;ref&lt;/u&gt;" in cap
    assert "#x_y_z&lt;" in cap


def test_archive_caption_escapes_reason() -> None:
    media_file = SimpleNamespace(
        request_number="260919-001",
        uploaded_at=dt.datetime(2026, 9, 19, 10, 0, tzinfo=dt.timezone.utc),
    )
    cap = _svc()._generate_archive_caption(media_file, "<script>x</script> & y")
    assert "<script>" not in cap
    assert "💬 &lt;script&gt;x&lt;/script&gt; &amp; y" in cap
    assert cap.startswith("🗄️ АРХИВ\n📋 #260919-001")


def test_no_raw_free_text_interpolation_left() -> None:
    """Ратчет: в функциях подписей свободные поля не подставляются «как есть»."""
    for fn in (
        MediaStorageService._generate_caption,
        MediaStorageService._generate_domain_caption,
        MediaStorageService._generate_archive_caption,
    ):
        src = inspect.getsource(fn)
        for raw in ("{description}", "{ref}", "{archive_reason}", "{tag}", "{t}"):
            assert raw not in src, f"{fn.__name__}: сырой {raw} без html.escape"
