"""П6b / AUD3-09 — таймауты обращений к Telegram: профиль на операцию.

Формулировка пункта («нет и глобальной защиты») **опровергнута замером**: у
aiogram 3.30 сессия по умолчанию сдаётся за 60 с. Реальный дефект другой —
рассылки идут ПОСЛЕДОВАТЕЛЬНО по получателям, поэтому деградировавший
Telegram превращался в N × 60 с, и `deliver_feedback_to_managers` ждал этого
прямо внутри HTTP-обработчика жителя.

Стенд — TCP-сервер, который принимает соединение и не отвечает: обычный
«сервер лёг» даёт мгновенный ECONNREFUSED и ничего не проверяет.

⚠️ Все временные проверки смотрят на ПРОШЕДШЕЕ ВРЕМЯ, а не на факт исключения:
`pytest.raises` вокруг страховочного `wait_for` ловит собственную страховку
теста и зеленеет на неисправленном коде (обжигались в AUD3-08).
"""
from __future__ import annotations

import ast
import asyncio
import socket
import time
from pathlib import Path

import pytest

from uk_management_bot.services import notification_service as ns
from uk_management_bot.utils import telegram_client as tc

TOKEN = "123456789:AAEeTestTokenValueForUnitTestsOnly00"
SAFETY = 30  # заведомо больше исправленных порогов и меньше дефолтных 60 с


@pytest.fixture
def hung_telegram(monkeypatch):
    """ЛЮБАЯ aiohttp-сессия aiogram смотрит в порт, который не отвечает.

    Патчится сам класс, а не наша фабрика: иначе «обход фабрики» остаётся
    незамеченным — бот с сессией по умолчанию ушёл бы в настоящий
    api.telegram.org, получил мгновенный 401 и тест зеленел бы на
    неисправленном коде (проверено: именно так и было).
    """
    from aiogram.client.session.aiohttp import AiohttpSession
    from aiogram.client.telegram import TelegramAPIServer

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0))
    srv.listen(8)
    port = srv.getsockname()[1]
    hung = TelegramAPIServer(
        base=f"http://127.0.0.1:{port}/bot{{token}}/{{method}}",
        file=f"http://127.0.0.1:{port}/file/bot{{token}}/{{path}}",
    )

    original_init = AiohttpSession.__init__

    def _init(self, *args, **kwargs):
        kwargs["api"] = hung
        original_init(self, *args, **kwargs)

    monkeypatch.setattr(AiohttpSession, "__init__", _init)
    yield
    srv.close()


async def _elapsed(coro) -> float:
    """Время до возврата/исключения; страховка не даёт висеть в CI вечно."""
    started = time.monotonic()
    try:
        await asyncio.wait_for(coro, timeout=SAFETY)
    except Exception:
        pass
    return time.monotonic() - started


class TestSessionBackstop:
    pytestmark = pytest.mark.asyncio

    async def test_factory_bot_gives_up_far_sooner_than_aiogram_default(
        self, hung_telegram, monkeypatch
    ):
        """Любой вызов ограничен сессией фабрики, а не дефолтными 60 с."""
        monkeypatch.setattr(tc, "SESSION_TIMEOUT", 2.0)
        bot = tc.build_bot(TOKEN)
        try:
            elapsed = await _elapsed(bot.send_message(1, "x"))
        finally:
            await bot.session.close()

        assert elapsed < 10, (
            f"вызов длился {elapsed:.1f}s — сессия фабрики не применена, "
            "работает дефолт aiogram (60 с)"
        )

    async def test_zero_session_timeout_is_rejected(self, monkeypatch):
        """Ноль — не «без ограничений», а отключение защиты.

        При `session.timeout == 0` aiogram не передаёт `request_timeout` в
        long-polling (`if bot.session.timeout:`), и предела не остаётся.
        """
        monkeypatch.setattr(tc, "SESSION_TIMEOUT", 0)
        with pytest.raises(ValueError):
            tc.build_bot(TOKEN)


class TestPerCallProfiles:
    pytestmark = pytest.mark.asyncio

    async def test_broadcast_send_is_shorter_than_the_session_backstop(
        self, hung_telegram, monkeypatch
    ):
        """`send_to_user` — рассылочный путь: свой короткий предел."""
        monkeypatch.setattr(tc, "SESSION_TIMEOUT", 20.0)
        monkeypatch.setattr(ns.channel, "SEND_TIMEOUT", 1.0)
        bot = tc.build_bot(TOKEN)
        try:
            elapsed = await _elapsed(ns.send_to_user(bot, 1, "x"))
        finally:
            await bot.session.close()

        assert elapsed < 5, (
            f"отправка длилась {elapsed:.1f}s — per-call таймаут не передан, "
            "вызов упёрся в общий сессионный предел"
        )

    async def test_broadcast_total_scales_with_per_call_not_with_backstop(
        self, hung_telegram, monkeypatch
    ):
        """Суть пункта: N получателей не умножают СЕССИОННЫЙ предел.

        Без per-call таймаута три получателя дали бы 3 × 20 с и упёрлись бы в
        страховку теста; с ним — примерно 3 × 1 с.
        """
        monkeypatch.setattr(tc, "SESSION_TIMEOUT", 20.0)
        monkeypatch.setattr(ns.feedback, "SEND_TIMEOUT", 1.0)
        monkeypatch.setattr(ns.feedback, "_resolve_channel_id", lambda: None)
        bot = tc.build_bot(TOKEN)
        try:
            elapsed = await _elapsed(
                ns.deliver_feedback_to_managers(
                    bot, telegram_ids=[1, 2, 3], text="hi", photo=None
                )
            )
        finally:
            await bot.session.close()

        assert elapsed < 10, (
            f"рассылка трём получателям заняла {elapsed:.1f}s — предел одного "
            "вызова накапливается по получателям"
        )

    async def test_photo_upload_gets_a_longer_budget_than_text(self, monkeypatch):
        """Загрузка байтов легитимно дольше текста — иначе рвём нормальное фото."""
        calls: dict[str, float | None] = {}

        class _Msg:
            photo = None

        class _Bot:
            async def send_message(self, *a, **kw):
                calls["message"] = kw.get("request_timeout")

            async def send_photo(self, *a, **kw):
                calls["photo"] = kw.get("request_timeout")
                return _Msg()

        monkeypatch.setattr(ns.feedback, "_resolve_channel_id", lambda: None)
        await ns.deliver_feedback_to_managers(
            _Bot(), telegram_ids=[1], text="hi", photo=b"rawbytes"
        )
        await ns.deliver_feedback_to_managers(
            _Bot(), telegram_ids=[1], text="hi", photo=None
        )

        assert calls["photo"] == tc.UPLOAD_TIMEOUT
        assert calls["message"] == tc.SEND_TIMEOUT
        assert tc.UPLOAD_TIMEOUT > tc.SEND_TIMEOUT


class TestLongPollingStaysAlive:
    pytestmark = pytest.mark.asyncio

    async def test_polling_request_timeout_exceeds_the_poll_duration(self):
        """Гейт против «прикрутить таймаут и порвать длинный опрос».

        Формулу считает САМ aiogram (`session.timeout + polling_timeout`),
        поэтому здесь она не переписывается, а исполняется: гоняем настоящий
        `Dispatcher._listen_updates` с ботом-заглушкой и смотрим, что реально
        уехало в запрос.
        """
        from aiogram.dispatcher.dispatcher import Dispatcher

        seen: dict = {}
        poll_seconds = 30

        class _Session:
            timeout = tc.SESSION_TIMEOUT

        class _StubBot:
            session = _Session()

            async def __call__(self, method, **kwargs):
                seen.update(kwargs)
                raise asyncio.CancelledError

        gen = Dispatcher._listen_updates(_StubBot(), polling_timeout=poll_seconds)
        with pytest.raises(asyncio.CancelledError):
            await gen.__anext__()

        assert seen.get("request_timeout", 0) > poll_seconds, (
            "запас на длинный опрос исчез: aiogram оборвёт getUpdates раньше, "
            f"чем Telegram ответит ({seen})"
        )


PACKAGE_ROOT = Path(__file__).resolve().parents[2] / "uk_management_bot"
FACTORY_FILE = "uk_management_bot/utils/telegram_client.py"


def _bot_constructions(tree: ast.AST) -> list[int]:
    return [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "Bot"
    ]


def test_bot_is_constructed_only_by_the_factory():
    """Иначе профили таймаутов разъедутся по конструкторам (как было).

    До этого пункта `Bot(...)` собирался в трёх местах, и они уже разошлись:
    два с `parse_mode=HTML`, ленивый fallback — без него. Расхождение никто
    не замечал, потому что и заметить было негде.
    """
    offenders = []
    for path in PACKAGE_ROOT.rglob("*.py"):
        rel = path.relative_to(PACKAGE_ROOT.parent).as_posix()
        if rel == FACTORY_FILE or "tests" in path.parts or "venv" in path.parts:
            continue
        for lineno in _bot_constructions(ast.parse(path.read_text(encoding="utf-8"))):
            offenders.append(f"{rel}:{lineno}")

    assert not offenders, (
        "Bot(...) собран мимо utils/telegram_client.build_bot — сессия такого "
        f"бота останется с дефолтом 60 с: {offenders}"
    )
