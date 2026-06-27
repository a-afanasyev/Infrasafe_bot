"""Хелперы для тестов access-загрузки: фейковый Telegram-клиент и фейк Message.

Telegram МОКается полностью — реальные каналы/сеть не нужны (см. conftest.py).
"""
import uuid
from types import SimpleNamespace


def make_fake_message(file_id=None, chat_id=-1001234567890, message_id=777, caption="cap"):
    """Минимальный фейк aiogram.types.Message для пути сохранения метаданных."""
    photo = [SimpleNamespace(file_id=file_id or f"TGFILE-{uuid.uuid4().hex[:12]}")]
    return SimpleNamespace(
        photo=photo,
        video=None,
        document=None,
        chat=SimpleNamespace(id=chat_id),
        message_id=message_id,
        caption=caption,
    )


class FakeTelegram:
    """Фейк TelegramClientService: пишет историю вызовов, возвращает фейк Message."""

    def __init__(self):
        self.send_photo_calls = []
        self.send_video_calls = []
        self.send_document_calls = []

    async def send_photo(self, chat_id, photo, caption=None, **kwargs):
        self.send_photo_calls.append({"chat_id": chat_id, "caption": caption})
        return make_fake_message(caption=caption)

    async def send_video(self, chat_id, video, caption=None, **kwargs):
        self.send_video_calls.append({"chat_id": chat_id, "caption": caption})
        return make_fake_message(caption=caption)

    async def send_document(self, chat_id, document, caption=None, **kwargs):
        self.send_document_calls.append({"chat_id": chat_id, "caption": caption})
        return make_fake_message(caption=caption)

    async def close(self):
        pass
