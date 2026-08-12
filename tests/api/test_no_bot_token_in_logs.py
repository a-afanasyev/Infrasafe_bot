"""Токен бота не попадает в логи через текст исключения httpx.

Утечка возможна не через наш f-string, а через **сообщение исключения**:
`raise_for_status()` кладёт в текст полный URL запроса, а URL Bot API содержит
токен целиком. Проверено на живом API-контейнере profk:

    str(e) = Server error '500 …' for url
             'https://api.telegram.org/bot<ТОКЕН>/getFile?file_id=X'

Срабатывает на любом ответе Telegram, кроме 2xx и явно обработанного 400 —
то есть на 429 (rate limit), 401 после ротации токена, 5xx. Токен бота даёт
чтение всех апдейтов, отправку от имени бота и скачивание любого файла,
который бот видел, поэтому его место — не в логах.

Здесь проверяются САМИ call-site'ы. Фильтр логов (`SecurityFilter`) чинится
отдельно и служит защитой в глубину — тесты на него в
`uk_management_bot/tests/utils/test_structured_logger.py`. Одного фильтра мало:
он активен только при `DEBUG=False`, и полагаться на регэксп вместо того,
чтобы не логировать секрет, — не защита, а надежда.
"""
import logging
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.user_verification import (
    DocumentType, UserDocument,
)

pytestmark = pytest.mark.asyncio

BASE = "/api/v2/residents"

#: Синтетический токен реалистичной формы `<id>:<секрет>`.
FAKE_TOKEN = "7712345678:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw"
FAKE_SECRET = FAKE_TOKEN.split(":", 1)[1]


@pytest_asyncio.fixture(autouse=True)
def _mute_telegram():
    with patch("uk_management_bot.api.residents.notify._send", new=AsyncMock()):
        yield


async def _resident(db, tg) -> User:
    u = User(telegram_id=tg, first_name="Л", last_name=str(tg), roles='["applicant"]',
             active_role="applicant", status="approved", language="ru",
             verification_status="pending")
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


async def _doc(db, user_id) -> UserDocument:
    d = UserDocument(user_id=user_id, document_type=DocumentType.PASSPORT,
                     file_id="AgACSECRET", file_name="passport.jpg", file_size=1024)
    db.add(d)
    await db.commit()
    await db.refresh(d)
    return d


def _raising_client(exc: Exception):
    """httpx.AsyncClient, у которого getFile падает переданным исключением."""
    class _C:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, params=None):
            raise exc

        def stream(self, method, url):  # pragma: no cover — до стрима не доходим
            raise AssertionError("не должно вызываться")
    return _C


def _status_error() -> httpx.HTTPStatusError:
    """Ровно то исключение, которое поднимает `raise_for_status()` на 5xx."""
    request = httpx.Request(
        "GET", f"https://api.telegram.org/bot{FAKE_TOKEN}/getFile",
        params={"file_id": "AgACSECRET"},
    )
    response = httpx.Response(500, request=request)
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as e:
        return e
    raise AssertionError("raise_for_status не поднял исключение")  # pragma: no cover


class TestDocumentProxyLogging:

    async def test_token_absent_from_logs_on_telegram_5xx(
        self, client: AsyncClient, db_session: AsyncSession, caplog,
    ):
        resident = await _resident(db_session, 7401)
        doc = await _doc(db_session, resident.id)
        exc = _status_error()
        assert FAKE_SECRET in str(exc), "предпосылка теста: httpx кладёт URL в текст"

        with caplog.at_level(logging.WARNING):
            with patch("uk_management_bot.api.residents.documents.httpx.AsyncClient",
                       _raising_client(exc)):
                r = await client.get(f"{BASE}/{resident.id}/documents/{doc.id}/file")

        assert r.status_code == 502
        logged = "\n".join(rec.getMessage() for rec in caplog.records)
        assert FAKE_SECRET not in logged
        assert FAKE_TOKEN not in logged
        assert "7712345678" not in logged, "id бота — тоже часть токена"

    async def test_failure_is_still_diagnosable(
        self, client: AsyncClient, db_session: AsyncSession, caplog,
    ):
        """Убрать секрет — не значит ослепить дежурного.

        В логе обязаны остаться: что сломалось (id документа и жителя) и чем
        именно (класс исключения). Иначе лечение утечки оплачено отладкой.
        """
        resident = await _resident(db_session, 7402)
        doc = await _doc(db_session, resident.id)

        with caplog.at_level(logging.WARNING):
            with patch("uk_management_bot.api.residents.documents.httpx.AsyncClient",
                       _raising_client(_status_error())):
                await client.get(f"{BASE}/{resident.id}/documents/{doc.id}/file")

        logged = "\n".join(rec.getMessage() for rec in caplog.records)
        assert str(doc.id) in logged
        assert "HTTPStatusError" in logged

    async def test_token_absent_on_network_error(
        self, client: AsyncClient, db_session: AsyncSession, caplog,
    ):
        """Транспортные ошибки httpx тоже носят с собой request — и URL."""
        resident = await _resident(db_session, 7403)
        doc = await _doc(db_session, resident.id)
        request = httpx.Request("GET", f"https://api.telegram.org/bot{FAKE_TOKEN}/getFile")
        exc = httpx.ConnectTimeout(
            f"timed out for url https://api.telegram.org/bot{FAKE_TOKEN}/getFile",
            request=request,
        )

        with caplog.at_level(logging.WARNING):
            with patch("uk_management_bot.api.residents.documents.httpx.AsyncClient",
                       _raising_client(exc)):
                r = await client.get(f"{BASE}/{resident.id}/documents/{doc.id}/file")

        assert r.status_code == 502
        logged = "\n".join(rec.getMessage() for rec in caplog.records)
        assert FAKE_SECRET not in logged


class TestInviteBotUsernameLogging:
    """Предсуществующий сайт с тем же дефектом: `getMe` при выдаче инвайт-ссылки
    (`api/shifts/router/_helpers.py`) логировал сырое исключение тем же способом."""

    async def test_token_absent_from_logs(self, caplog):
        from uk_management_bot.api.shifts import router as shifts_router
        from uk_management_bot.config.settings import settings

        request = httpx.Request("GET", f"https://api.telegram.org/bot{FAKE_TOKEN}/getMe")
        response = httpx.Response(401, request=request)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            boom = exc

        # Хелпер уходит в сеть только когда username не закэширован, а токен есть.
        with patch.object(settings, "BOT_USERNAME", None), \
                patch.object(settings, "BOT_TOKEN", FAKE_TOKEN), \
                caplog.at_level(logging.ERROR):
            # AUD5-ARCH-3 волна 8: httpx импортирован в _helpers-модуле пакета —
            # патчим модуль РЕЗОЛВА имени, а не пакет (реэкспорт httpx из
            # __init__ был бы мусорным namespace).
            with patch("uk_management_bot.api.shifts.router._helpers.httpx.AsyncClient",
                       _raising_client(boom)):
                result = await shifts_router._resolve_bot_username()

        assert result is None
        logged = "\n".join(rec.getMessage() for rec in caplog.records)
        assert FAKE_SECRET not in logged
        assert "7712345678" not in logged
