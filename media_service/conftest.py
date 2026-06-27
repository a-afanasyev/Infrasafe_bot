"""Pytest fixtures для unit/integration тестов media_service.

ЗАПУСК (Telegram-клиент МОКается, реальные TG-каналы не нужны):

    docker run --rm \
      -e DEBUG=true \
      -e TELEGRAM_BOT_TOKEN=123456789:AA-test-token \
      -e DATABASE_URL=sqlite:////tmp/uk_media_test.db \
      -e MEDIA_API_KEYS=testkey \
      -v "$(pwd)":/app -w /app uk-media-service:latest \
      python -m pytest test_access_upload.py test_access_client.py -v

`Settings` грузится на уровне модуля (паттерн SEC-065/066), поэтому окружение
задаём ДО импорта app.* — через os.environ.setdefault здесь (переменные из
`docker run -e` имеют приоритет и не перетираются).
"""
import os

# DEBUG=true → отключает prod fail-fast (SEC-065/066/022) на старте config.py.
os.environ.setdefault("DEBUG", "true")
# Валидный по формату токен (aiogram.Bot валидирует `\d+:...`), сеть не дёргается.
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "123456789:AA-test-token")
# Файловый sqlite (НЕ :memory:) — get_db_context() открывает несколько
# соединений; in-memory sqlite приватен на соединение и потерял бы данные.
os.environ.setdefault("DATABASE_URL", "sqlite:////tmp/uk_media_test.db")
os.environ.setdefault("MEDIA_API_KEYS", "testkey")
os.environ.setdefault("ALLOWED_ORIGINS", "http://localhost")

import pytest


@pytest.fixture(autouse=True)
def _db_isolation():
    """Создаёт таблицы и чистит данные между тестами (изоляция)."""
    from app.models.media import Base, MediaFile, MediaChannel, MediaTag
    from app.db.database import engine, SessionLocal

    Base.metadata.create_all(bind=engine)
    yield
    s = SessionLocal()
    try:
        s.query(MediaFile).delete()
        s.query(MediaChannel).delete()
        s.query(MediaTag).delete()
        s.commit()
    finally:
        s.close()
