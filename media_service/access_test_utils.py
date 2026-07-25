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
    """Фейк TelegramClientService: пишет историю вызовов, возвращает фейк Message.

    fail_on: опциональное множество имён методов ({"get_file_url",
    "delete_message", "download_file"}), которые должны поднять исключение —
    используется тестами компенсации (сбой Telegram I/O в фазе 2 саги).
    """

    def __init__(self, fail_on=None):
        self.send_photo_calls = []
        self.send_video_calls = []
        self.send_document_calls = []
        self.get_file_url_calls = []
        self.delete_message_calls = []
        self.download_file_calls = []
        self.fail_on = fail_on or set()

    async def send_photo(self, chat_id, photo, caption=None, **kwargs):
        self.send_photo_calls.append({"chat_id": chat_id, "caption": caption})
        return make_fake_message(caption=caption)

    async def send_video(self, chat_id, video, caption=None, **kwargs):
        self.send_video_calls.append({"chat_id": chat_id, "caption": caption})
        return make_fake_message(caption=caption)

    async def send_document(self, chat_id, document, caption=None, **kwargs):
        self.send_document_calls.append({"chat_id": chat_id, "caption": caption})
        return make_fake_message(caption=caption)

    async def get_file_url(self, file_id):
        self.get_file_url_calls.append(file_id)
        if "get_file_url" in self.fail_on:
            raise RuntimeError("simulated get_file_url failure")
        return f"https://example.invalid/file/{file_id}"

    async def delete_message(self, chat_id, message_id):
        self.delete_message_calls.append({"chat_id": chat_id, "message_id": message_id})
        if "delete_message" in self.fail_on:
            raise RuntimeError("simulated delete_message failure")
        return True

    async def download_file(self, file_id):
        self.download_file_calls.append(file_id)
        if "download_file" in self.fail_on:
            raise RuntimeError("simulated download_file failure")
        return b"\x89PNG\r\n\x1a\nfakebytes", "image/png"

    async def close(self):
        pass
