"""
Shared fixtures for API tests.

Uses an in-memory aiosqlite database and overrides FastAPI dependencies
so that tests run without Docker / PostgreSQL / JWT tokens.
"""
import os

# PR-5: сохранить реальный postgres-DATABASE_URL процесса для PG-гонок
# (test_webhook_outbox_pg_concurrency) ДО того, как tests/services/conftest.py
# перетрёт env на sqlite. Conftest'ы аргументов импортируются в порядке
# аргументов — при каноническом `pytest tests/api tests/services` этот файл
# грузится первым. Пробрасываем через отдельную env-переменную (tests/api —
# НЕ пакет, импортировать conftest напрямую нельзя); POSTGRES_TEST_URL можно
# задать и снаружи как явный override.
if "POSTGRES_TEST_URL" not in os.environ and os.getenv("DATABASE_URL", "").startswith("postgresql"):
    os.environ["POSTGRES_TEST_URL"] = os.environ["DATABASE_URL"]

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from uk_management_bot.database.session import Base
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.yard import Yard  # noqa: F401  # register tables for create_all
from uk_management_bot.database.models.building import Building  # noqa: F401  # register tables for create_all
from uk_management_bot.database.models.apartment import Apartment  # noqa: F401  # register tables for create_all
from uk_management_bot.database.models.user_apartment import UserApartment  # noqa: F401  # register tables for create_all
from uk_management_bot.database.models.work_report import WorkReport  # noqa: F401  # register tables for create_all

from uk_management_bot.api.main import app
from uk_management_bot.api.dependencies import get_db, get_current_user

# ── In-memory async engine ──────────────────────────────────────────

TEST_DB_URL = "sqlite+aiosqlite://"

_test_manager: User | None = None


@pytest_asyncio.fixture
async def db_engine():
    engine = create_async_engine(TEST_DB_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session_factory(db_engine):
    factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    return factory


@pytest_asyncio.fixture
async def db_session(db_session_factory):
    async with db_session_factory() as session:
        yield session


# ── Seed a manager user ─────────────────────────────────────────────

@pytest_asyncio.fixture
async def manager_user(db_session: AsyncSession):
    global _test_manager
    user = User(
        telegram_id=999999,
        username="testmanager",
        first_name="Test",
        last_name="Manager",
        roles='["manager"]',
        active_role="manager",
        status="approved",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    _test_manager = user
    return user


# ── Seed a regular user (for moderation tests) ──────────────────────

@pytest_asyncio.fixture
async def resident_user(db_session: AsyncSession):
    user = User(
        telegram_id=888888,
        username="testresident",
        first_name="Resident",
        last_name="User",
        roles='["applicant"]',
        active_role="applicant",
        status="approved",
        phone="+79001234567",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


# ── FastAPI test client with dependency overrides ────────────────────

@pytest_asyncio.fixture
async def client(db_session_factory, manager_user):
    """HTTP client with overridden DB and auth dependencies."""

    async def override_get_db():
        async with db_session_factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise

    async def override_get_current_user():
        return manager_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


# ── Reset the public-board TTL cache between tests ──────────────────
# /api/v2/public/board memoizes its payload in a module-level variable;
# without this reset a cached result leaks across tests.

@pytest.fixture(autouse=True)
def _reset_public_board_cache():
    import uk_management_bot.api.public.router as public_router
    public_router._board_cache = None
    yield
    public_router._board_cache = None


# ── Reset the slowapi rate-limiter between tests ────────────────────
# The limiter is a module-level singleton with shared counters (Redis in
# the dev container, in-memory in CI). Without a reset, per-IP counters
# accumulate across tests — all requests share one client identity — so a
# test asserting a first-request 200 flakes into 429 once an earlier test
# has spent the quota. Reset both before and after to isolate every test.

@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    from uk_management_bot.api.rate_limit import limiter
    try:
        limiter.reset()
    except Exception:
        pass
    yield
    try:
        limiter.reset()
    except Exception:
        pass


# ── Telegram Bot API: подмена транспорта общего клиента (A9-P2-9) ────
# Все вызовы Bot API из API-процесса идут через `api/telegram_send.py`.
# Тесты подменяют не модуль, а транспорт httpx его общего клиента — так
# проверяется реальный wire (URL-метод, JSON, parse_mode) и классификация.
# По умолчанию (autouse) сеть закрыта: ответ как у Telegram на невалидный
# токен (404 ok=false) — тот же исход, что давал живой вызов с ci-токеном.


class TelegramStub:
    """Записывает запросы к Bot API и отвечает заданным `handler`."""

    def __init__(self):
        self.requests: list = []
        self.handler = lambda request: _tg_json(404, ok=False, description="Not Found")

    def dispatch(self, request):
        self.requests.append(request)
        return self.handler(request)

    def calls(self, method: str) -> list[dict]:
        """JSON-тела вызовов метода Bot API (`sendMessage`, `getFile`, …)."""
        import json

        return [
            json.loads(r.content or b"{}") for r in self.requests
            if r.url.path.rsplit("/", 1)[-1] == method and "/file/" not in r.url.path
        ]

    def reply(self, status_code: int = 200, **body):
        self.handler = lambda request: _tg_json(status_code, **body)


def _tg_json(status_code: int, **body):
    import httpx

    body.setdefault("ok", 200 <= status_code < 300)
    if not body["ok"]:
        body.setdefault("error_code", status_code)
    return httpx.Response(status_code, json=body)


@pytest_asyncio.fixture(autouse=True)
async def telegram_api():
    # Без `monkeypatch`: autouse-фикстура conftest'а, запросившая monkeypatch,
    # сдвигает его teardown ПОСЛЕ модульных autouse-фикстур (например,
    # `restore_module` в test_rate_limit_trusted_proxies перечитал бы модуль
    # ещё с «грязным» env). Транспорт ставим и снимаем вручную.
    import httpx

    from uk_management_bot.api import telegram_send

    stub = TelegramStub()
    previous = telegram_send._transport
    await telegram_send.aclose()
    telegram_send._transport = httpx.MockTransport(stub.dispatch)
    try:
        yield stub
    finally:
        telegram_send._transport = previous
        await telegram_send.aclose()


# ── Сеть вне транзакции и после ответа (A9-P2-7/P2-8) ────────────────
# httpx.ASGITransport отдаёт ответ только после ВСЕГО ASGI-вызова, включая
# BackgroundTasks, — «ответ не ждёт Telegram» им не проверить. Здесь — сырой
# ASGI-вызов: в общий журнал `log` пишется "response" в момент отправки
# последнего куска тела; шпионы сетевых вызовов пишут туда же — порядок
# записей и есть проверка. `RecordingSessions` — фабрика сессий для override
# `get_db`, помнящая выданные сессии: шпион сети спрашивает
# `any_in_transaction()` — держит ли кто-то из них транзакцию в момент вызова.


class RecordingSessions:
    def __init__(self, factory):
        self._factory = factory
        self.sessions: list = []

    def __call__(self):
        session = self._factory()
        self.sessions.append(session)
        return session

    def any_in_transaction(self) -> bool:
        return any(s.in_transaction() for s in self.sessions)


@pytest.fixture
def recording_db(db_session_factory):
    """Override `get_db` на запоминающую фабрику (пользователя задаёт тест)."""
    rec = RecordingSessions(db_session_factory)

    async def override_get_db():
        async with rec() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db
    yield rec
    app.dependency_overrides.clear()


@pytest.fixture
def asgi_call():
    """``await asgi_call(method, path, log, json=None) -> (status, body)``."""
    import asyncio
    import json as _json

    async def _call(method: str, path: str, log: list, json=None):
        body = b"" if json is None else _json.dumps(json).encode()
        headers = [(b"host", b"test"), (b"content-length", str(len(body)).encode())]
        if json is not None:
            headers.append((b"content-type", b"application/json"))
        scope = {
            "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
            "method": method, "scheme": "http", "path": path,
            "raw_path": path.encode(), "query_string": b"", "root_path": "",
            "headers": headers, "client": ("127.0.0.1", 50000),
            "server": ("test", 80),
        }
        done = asyncio.Event()
        request_sent = False
        status: dict = {}
        chunks: list[bytes] = []

        async def receive():
            nonlocal request_sent
            if not request_sent:
                request_sent = True
                return {"type": "http.request", "body": body, "more_body": False}
            await done.wait()
            return {"type": "http.disconnect"}

        async def send(message):
            if message["type"] == "http.response.start":
                status["code"] = message["status"]
            elif message["type"] == "http.response.body":
                chunks.append(message.get("body", b""))
                if not message.get("more_body", False):
                    log.append("response")
                    done.set()

        await app(scope, receive, send)
        raw = b"".join(chunks)
        return status["code"], (_json.loads(raw) if raw else None)

    return _call
