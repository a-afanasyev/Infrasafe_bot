"""
Telegram клиент для работы с каналами
"""

import asyncio
import enum
from dataclasses import dataclass
import logging
import time
from typing import Optional, Union, Tuple
import httpx
from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.types import InputFile, BufferedInputFile, Message
from aiogram.exceptions import (
    AiogramError,
    TelegramAPIError,
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNotFound,
)

from app.core.config import settings
from app.core.log_sanitize import TelegramDownloadError, describe_http_error

logger = logging.getLogger(__name__)

# Паузы перед 2-й и 3-й попытками download_file (первая — сразу). Вынесены в
# константу, чтобы тест мог посчитать худший случай против бюджета edge.
DOWNLOAD_BACKOFF_SECONDS: Tuple[float, ...] = (0.0, 0.5, 1.5)

# Часы общего deadline — отдельным именем, чтобы тест худшего случая мог
# «проматывать» время попыток без реальных 15- и 20-секундных ожиданий.
_monotonic = time.monotonic

# Текст Bot API для delete_message по уже удалённому сообщению.
_MESSAGE_ALREADY_GONE = "message to delete not found"


class DeleteOutcome(enum.Enum):
    """A9-P3-23: итог delete_message — категория, а не bool.

    Сага удаления по-разному реагирует на «удалить нельзя никогда» и «не
    получилось сейчас»: первое повтор не лечит, второе — лечит.
    """

    DELETED = "deleted"            # сообщение удалено
    ALREADY_GONE = "already_gone"  # сообщения уже нет — конечное состояние достигнуто
    UNDELETABLE = "undeletable"    # permanent: нет прав, старше 48 ч, Forbidden, чат недоступен
    TRANSIENT = "transient"        # сеть, таймаут, 5xx, 429 — повтор может помочь


@dataclass(frozen=True)
class DeleteResult:
    """Итог delete_message: категория + причина отказа (текст Telegram)."""

    outcome: DeleteOutcome
    reason: Optional[str] = None


def _classify_delete_error(exc: BaseException) -> DeleteOutcome:
    """Отказ Telegram → категория. 400/403/404 — ответ по существу запроса
    (повтор даст то же самое); всё прочее (TelegramNetworkError, ServerError,
    RetryAfter, таймаут, неизвестное) — transient: осторожная сторона, строка
    вернётся в active и вызывающий повторит."""
    if isinstance(exc, TelegramBadRequest):
        if _MESSAGE_ALREADY_GONE in str(exc).lower():
            return DeleteOutcome.ALREADY_GONE
        return DeleteOutcome.UNDELETABLE
    if isinstance(exc, (TelegramForbiddenError, TelegramNotFound)):
        return DeleteOutcome.UNDELETABLE
    return DeleteOutcome.TRANSIENT


def _download_timeout(read_cap: Optional[float] = None) -> httpx.Timeout:
    """BUG-189: connect и read — разные бюджеты.

    Одно число `timeout=60` заставляло ждать повисшее TCP-соединение с Telegram
    так же долго, как чтение большого файла, и ретрай стартовал уже после того,
    как edge-nginx (30 с) отдал браузеру 504.

    ``read_cap`` (AUD7-ARCH-03) — остаток общего бюджета: чтение не ждёт
    дольше, чем осталось до deadline.
    """
    connect = settings.telegram_download_connect_timeout_seconds
    read = settings.telegram_download_read_timeout_seconds
    if read_cap is not None:
        read = max(0.001, min(read, read_cap))
    return httpx.Timeout(
        connect=connect,
        read=read,
        write=connect,
        pool=connect,
    )


class TelegramClientService:
    """Сервис для работы с Telegram API"""

    def __init__(self):
        # BUG-189: дефолт aiogram-сессии — 60 с на любой вызов Bot API, включая
        # get_file перед скачиванием; тот же бюджет edge, что и у download_file.
        self.bot = Bot(
            token=settings.telegram_bot_token,
            session=AiohttpSession(timeout=settings.telegram_api_timeout_seconds),
        )
        # A9-P2-15: один httpx-клиент (пул соединений) на процесс — создаётся
        # лениво при первом скачивании, закрывается в close().
        self._http: Optional[httpx.AsyncClient] = None

    def _http_client(self) -> httpx.AsyncClient:
        """Общий httpx-клиент скачивания (ленивый: в тестах сервис строится
        через __new__, а httpx.AsyncClient подменяется)."""
        client = getattr(self, "_http", None)
        if client is None:
            client = httpx.AsyncClient(timeout=_download_timeout())
            self._http = client
        return client

    async def send_photo(
        self,
        chat_id: Union[int, str],
        photo: Union[InputFile, BufferedInputFile, str],
        caption: Optional[str] = None,
        parse_mode: Optional[str] = "HTML"
    ) -> Optional[Message]:
        """
        Отправка фото в канал
        """
        try:
            message = await self.bot.send_photo(
                chat_id=chat_id,
                photo=photo,
                caption=caption,
                parse_mode=parse_mode
            )
            logger.info(f"Photo sent to {chat_id}, message_id: {message.message_id}")
            return message

        except TelegramAPIError as e:
            logger.error(f"Failed to send photo to {chat_id}: {e}")
            raise

    async def send_video(
        self,
        chat_id: Union[int, str],
        video: Union[InputFile, BufferedInputFile, str],
        caption: Optional[str] = None,
        parse_mode: Optional[str] = "HTML"
    ) -> Optional[Message]:
        """
        Отправка видео в канал
        """
        try:
            message = await self.bot.send_video(
                chat_id=chat_id,
                video=video,
                caption=caption,
                parse_mode=parse_mode
            )
            logger.info(f"Video sent to {chat_id}, message_id: {message.message_id}")
            return message

        except TelegramAPIError as e:
            logger.error(f"Failed to send video to {chat_id}: {e}")
            raise

    async def send_document(
        self,
        chat_id: Union[int, str],
        document: Union[InputFile, BufferedInputFile, str],
        caption: Optional[str] = None,
        parse_mode: Optional[str] = "HTML"
    ) -> Optional[Message]:
        """
        Отправка документа в канал
        """
        try:
            message = await self.bot.send_document(
                chat_id=chat_id,
                document=document,
                caption=caption,
                parse_mode=parse_mode
            )
            logger.info(f"Document sent to {chat_id}, message_id: {message.message_id}")
            return message

        except TelegramAPIError as e:
            logger.error(f"Failed to send document to {chat_id}: {e}")
            raise

    async def edit_message_caption(
        self,
        chat_id: Union[int, str],
        message_id: int,
        caption: str,
        parse_mode: Optional[str] = "HTML"
    ) -> bool:
        """
        Редактирование подписи сообщения
        """
        try:
            await self.bot.edit_message_caption(
                chat_id=chat_id,
                message_id=message_id,
                caption=caption,
                parse_mode=parse_mode
            )
            logger.info(f"Caption updated for message {message_id} in {chat_id}")
            return True

        except TelegramAPIError as e:
            logger.error(f"Failed to edit caption for message {message_id} in {chat_id}: {e}")
            return False

    async def get_file(self, file_id: str):
        """
        Получение информации о файле
        """
        try:
            file_info = await self.bot.get_file(file_id)
            return file_info

        except TelegramAPIError as e:
            logger.error(f"Failed to get file info for {file_id}: {e}")
            raise

    async def get_file_url(self, file_id: str) -> Optional[str]:
        """
        Получение URL файла
        """
        try:
            file_info = await self.get_file(file_id)
            file_url = f"https://api.telegram.org/file/bot{settings.telegram_bot_token}/{file_info.file_path}"
            return file_url

        except Exception as e:
            # E1: сырое исключение несёт URL с токеном — логируем класс+статус.
            logger.error("Failed to get file URL for %s: %s", file_id, describe_http_error(e))
            return None

    async def download_file(self, file_id: str) -> Tuple[bytes, str]:
        """
        Download file bytes from Telegram by file_id.
        Returns (file_bytes, content_type).
        Token stays server-side — never exposed to clients.
        """
        # Семафор на весь путь скачивания (get_file + GET файла): без него одна
        # загрузка публичной витрины давала десятки одновременных обращений к
        # Telegram, а очередь из них выедала воркеры и пул соединений
        # (инцидент 2026-07-25, см. app/services/preview_cache.py).
        from app.services.preview_cache import download_semaphore

        # AUD7-ARCH-03: один общий deadline на очередь семафора, get_file, чтение
        # и все ретраи с backoff. asyncio.timeout обрывает повисший await (в том
        # числе ожидание слота), проверка остатка перед попыткой не даёт стартовать
        # той, что заведомо не уложится; при исчерпании — TelegramDownloadError
        # потребителю, а не 504 от edge на всё ещё живом запросе.
        budget = settings.telegram_download_total_budget_seconds
        deadline = _monotonic() + budget
        try:
            async with asyncio.timeout(budget):
                return await self._download_within_deadline(file_id, deadline, download_semaphore)
        except TimeoutError:
            raise TelegramDownloadError(
                f"download_file {file_id}: общий бюджет {budget:g} с исчерпан"
            ) from None

    async def _download_within_deadline(
        self, file_id: str, deadline: float, download_semaphore
    ) -> Tuple[bytes, str]:
        connect_timeout = settings.telegram_download_connect_timeout_seconds
        async with download_semaphore():
            # AUD6-P2-03: ретрай с backoff — сетевые сбои Telegram транзиентны,
            # а ретраев внутри media раньше не было вовсе (они жили только на
            # стороне потребителя, и не на всех путях). Клиентские 4xx (файл
            # удалён/недоступен) не ретраятся — повтор их не лечит.
            last_exc: Optional[Exception] = None
            for attempt, delay in enumerate(DOWNLOAD_BACKOFF_SECONDS, start=1):
                if delay:
                    await asyncio.sleep(delay)
                if _monotonic() + delay + connect_timeout > deadline:
                    # Остатка не хватит даже на установление соединения —
                    # поздняя попытка только продлила бы зависший запрос.
                    break
                try:
                    # Каждый шаг попытки — не дольше остатка общего бюджета.
                    file_info = await asyncio.wait_for(
                        self.get_file(file_id), timeout=max(0.001, deadline - _monotonic())
                    )
                    url = f"https://api.telegram.org/file/bot{settings.telegram_bot_token}/{file_info.file_path}"

                    timeout = _download_timeout(read_cap=deadline - _monotonic())
                    # A9-P2-15: общий клиент процесса, таймаут — на запрос
                    # (раньше новый AsyncClient на каждую попытку).
                    resp = await self._http_client().get(url, timeout=timeout)
                    resp.raise_for_status()

                    content_type = resp.headers.get("content-type", "application/octet-stream")
                    return resp.content, content_type
                except httpx.HTTPStatusError as e:
                    if e.response is not None and 400 <= e.response.status_code < 500:
                        # E1: `raise` исходного пронёс бы URL с токеном в traceback
                        # и в debug-ответ глобального хендлера. `from None` —
                        # осознанно: цепочка причин напечатала бы исходный текст.
                        raise TelegramDownloadError(
                            f"download_file {file_id}: {describe_http_error(e)}"
                        ) from None
                    last_exc = e
                    logger.warning("download_file %s: попытка %d не удалась: %s",
                                   file_id, attempt, describe_http_error(e))
                except (httpx.HTTPError, TelegramAPIError) as e:
                    last_exc = e
                    logger.warning("download_file %s: попытка %d не удалась: %s",
                                   file_id, attempt, describe_http_error(e))
                except TimeoutError as e:
                    # asyncio.wait_for вокруг get_file: Bot API не ответил в остаток.
                    last_exc = e
                    logger.warning("download_file %s: попытка %d — get_file не уложился в бюджет",
                                   file_id, attempt)
            if last_exc is None:
                raise TelegramDownloadError(
                    f"download_file {file_id}: общий бюджет исчерпан до первой попытки"
                )
            # E1: доминирующий путь (5xx/сеть после трёх попыток) — тоже без URL.
            raise TelegramDownloadError(
                f"download_file {file_id}: {describe_http_error(last_exc)}"
            ) from None

    async def delete_message(
        self,
        chat_id: Union[int, str],
        message_id: int
    ) -> DeleteResult:
        """
        Удаление сообщения. Не бросает: итог — DeleteResult с категорией
        DeleteOutcome (A9-P3-23), вызывающий обязан её разобрать.
        """
        try:
            await self.bot.delete_message(
                chat_id=chat_id,
                message_id=message_id
            )
            logger.info(f"Message {message_id} deleted from {chat_id}")
            return DeleteResult(DeleteOutcome.DELETED)

        # AiogramError: например, ClientDecodeError на 502 с HTML-телом — это не
        # TelegramAPIError, и без него «не бросает» нарушалось (QA A9-P3-32).
        except (TelegramAPIError, AiogramError, TimeoutError) as e:
            outcome = _classify_delete_error(e)
            if outcome is DeleteOutcome.ALREADY_GONE:
                logger.info("Message %s already absent in %s", message_id, chat_id)
            else:
                logger.error(
                    "Failed to delete message %s from %s (%s): %s",
                    message_id, chat_id, outcome.value, e,
                )
            return DeleteResult(outcome, reason=str(e) or type(e).__name__)

    async def get_chat(self, chat_id: Union[int, str]):
        """
        Получение информации о чате/канале
        """
        try:
            chat = await self.bot.get_chat(chat_id)
            return chat

        except TelegramAPIError as e:
            logger.error(f"Failed to get chat info for {chat_id}: {e}")
            raise

    async def close(self):
        """
        Закрытие соединения

        ARC-01: закрывать явно (`await close()` / async-context), НЕ из `__del__` —
        деструктор с `create_task(self.close())` на deprecated `get_event_loop()`
        мог оставить aiohttp-сессию незакрытой (утечка соединения) без сигнала.
        """
        await self.bot.session.close()
        http = getattr(self, "_http", None)
        if http is not None:
            self._http = None
            await http.aclose()


# A9-P2-15: процессный клиент. Раньше `get_storage_service()` строил новый
# Bot + AiohttpSession на КАЖДЫЙ запрос и никогда их не закрывал. Создаётся в
# lifespan (startup), закрывается на shutdown; ленивое создание — для путей без
# lifespan (TestClient без контекста, скрипты).
_shared_client: Optional[TelegramClientService] = None


def get_telegram_client() -> TelegramClientService:
    global _shared_client
    if _shared_client is None:
        _shared_client = TelegramClientService()
    return _shared_client


async def close_telegram_client() -> None:
    """Закрыть процессный клиент (aiohttp-сессия Bot + httpx). Идемпотентно."""
    global _shared_client
    client, _shared_client = _shared_client, None
    if client is not None:
        await client.close()