"""П6a / AUD3-08 — таймауты Redis: два разных профиля, а не один.

Дефект: ни у одного из шести call-site нет таймаутов. Зависший (принимающий
TCP, но не отвечающий) Redis блокирует вызывающего навсегда — а publisher
дёргается прямо из обработчика HTTP-запроса.

Почему нельзя просто выставить `socket_timeout` всем: у подписчика операция
чтения ЖДЁТ ПО ЗАМЫСЛУ. `listen()` на тихом канале обязан висеть часами, и
операционный таймаут порвёт живое соединение на первой же паузе. Поэтому:

* **publisher / ping** — `socket_connect_timeout` + `socket_timeout`
  (короткий round-trip, ждать вечно нельзя);
* **subscriber** — `socket_connect_timeout` + `health_check_interval`, БЕЗ
  `socket_timeout`; сам handshake `subscribe()` ограничен `wait_for`.

Тест тихой подписки здесь — обязательный гейт против «слепого» исправления:
он краснеет ровно тогда, когда подписчику выставили операционный таймаут.
"""
import asyncio
import os
import socket
import time

import pytest

from uk_management_bot.services import redis_pubsub as rp

pytestmark = pytest.mark.asyncio

REDIS_URL = os.getenv("REDIS_URL", "")
requires_redis = pytest.mark.skipif(
    not REDIS_URL.startswith("redis://"),
    reason="нужен живой Redis (REDIS_URL); в каноническом прогоне он есть",
)


@pytest.fixture
def black_hole():
    """TCP-порт, который принимает соединение и НИКОГДА не отвечает.

    Именно этот режим отказа и опасен: обычный «сервер лёг» даёт мгновенный
    ECONNREFUSED, а зависший — бесконечное ожидание.
    """
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0))
    srv.listen(8)
    yield f"redis://127.0.0.1:{srv.getsockname()[1]}/0"
    srv.close()


class TestPublisherProfile:
    async def test_publish_to_a_hung_server_does_not_block_forever(
        self, black_hole, monkeypatch
    ):
        """Главный тест пункта: publisher обязан сдаться, а не висеть.

        Ограничение сверху заведомо больше операционного таймаута, но много
        меньше «навсегда»: без фикса тест падает по этому wait_for.
        """
        monkeypatch.setattr(rp, "_redis_client", None)
        monkeypatch.setattr(
            type(rp.settings), "REDIS_PUBSUB_URL_RESOLVED",
            property(lambda self: black_hole),
        )

        started = time.monotonic()
        await asyncio.wait_for(
            rp.publish_request_event("test.event", {"x": 1}), timeout=15
        )
        elapsed = time.monotonic() - started

        # publish_* намеренно fail-soft (уведомление не дошло — не повод ронять
        # запрос), поэтому проверяем не исключение, а то, что вернулся быстро.
        assert elapsed < 10, f"publisher висел {elapsed:.1f}s — таймаута нет"

    async def test_publisher_client_carries_both_timeouts(self, monkeypatch):
        """Профиль publisher: и connect, и операция ограничены."""
        captured = {}

        def _fake_from_url(url, **kwargs):
            captured.update(kwargs)

            class _C:
                async def ping(self):
                    return True

                async def publish(self, *a):
                    return 1

            return _C()

        monkeypatch.setattr(rp, "_redis_client", None)
        monkeypatch.setattr(rp.aioredis, "from_url", _fake_from_url)
        await rp.get_pubsub_redis()

        assert captured.get("socket_connect_timeout"), "нет connect-таймаута"
        assert captured.get("socket_timeout"), "нет операционного таймаута"


SUBSCRIBERS = [
    ("requests", "subscribe_to_requests"),
    ("shifts", "subscribe_to_shifts"),
    ("buildings", "subscribe_to_buildings"),
    ("yards", "subscribe_to_yards"),
    ("apartments", "subscribe_to_apartments"),
]


class TestSubscriberProfile:
    @pytest.mark.parametrize("name,fn", SUBSCRIBERS, ids=[s[0] for s in SUBSCRIBERS])
    async def test_subscriber_has_connect_timeout_but_no_operation_timeout(
        self, name, fn, monkeypatch
    ):
        """Все пять фабрик обязаны нести ОДИН профиль — иначе они разъедутся."""
        captured = {}

        def _fake_from_url(url, **kwargs):
            captured.update(kwargs)

            class _PS:
                async def subscribe(self, *a):
                    return None

            class _C:
                def pubsub(self):
                    return _PS()

                async def aclose(self):
                    return None

            return _C()

        monkeypatch.setattr(rp.aioredis, "from_url", _fake_from_url)
        await getattr(rp, fn)()

        assert captured.get("socket_connect_timeout"), f"{name}: нет connect-таймаута"
        assert "socket_timeout" not in captured or captured["socket_timeout"] is None, (
            f"{name}: операционный таймаут на подписчике порвёт тихий канал — "
            "listen() ждёт по замыслу"
        )
        assert captured.get("health_check_interval"), (
            f"{name}: без health-check мёртвое соединение не обнаружится, "
            "а операционного таймаута тут быть не должно"
        )

    async def test_failed_subscribe_closes_the_connection(self, black_hole, monkeypatch):
        """Неудачная подписка не должна оставлять висящее соединение.

        Прежний код при исключении в `subscribe()` терял клиента: соединение
        оставалось открытым, а вернуть его было уже некому.
        """
        closed = {"n": 0}

        def _fake_from_url(url, **kwargs):
            class _PS:
                async def subscribe(self, *a):
                    raise ConnectionError("redis недоступен")

            class _C:
                def pubsub(self):
                    return _PS()

                async def aclose(self):
                    closed["n"] += 1

            return _C()

        monkeypatch.setattr(rp.aioredis, "from_url", _fake_from_url)
        with pytest.raises(Exception):
            await rp.subscribe_to_requests()
        assert closed["n"] == 1, "клиент не закрыт после неудачной подписки"

    async def test_subscribe_handshake_to_a_hung_server_gives_up(self, black_hole, monkeypatch):
        """Сам `subscribe()` тоже ограничен — иначе висит на мёртвом сервере.

        ⚠️ Проверяется ВРЕМЯ, а не факт исключения: `pytest.raises(Exception)`
        вокруг `wait_for` поймал бы собственный страховочный таймаут теста и
        был бы зелёным на никак не исправленном коде (проверено — был).
        """
        monkeypatch.setattr(
            type(rp.settings), "REDIS_PUBSUB_URL_RESOLVED",
            property(lambda self: black_hole),
        )
        started = time.monotonic()
        with pytest.raises(Exception):
            await asyncio.wait_for(rp.subscribe_to_requests(), timeout=20)
        elapsed = time.monotonic() - started
        assert elapsed < 15, (
            f"handshake сдался за {elapsed:.1f}s — это сработала страховка теста, "
            "а не собственный предел subscribe()"
        )


@requires_redis
class TestQuietSubscriptionSurvives:
    """ГЕЙТ против «слепого» исправления (плана §П6a).

    Краснеет ровно тогда, когда подписчику выставили операционный таймаут:
    несколько секунд тишины не должны рвать соединение.
    """

    async def test_silence_then_message_via_listen(self):
        """Читаем ИМЕННО через `listen()` — так делает прод (`ws/router._pump_pubsub`).

        Это не придирка к стилю. Проверено эмпирически: при чтении через
        `get_message(timeout=1.0)` подписка переживает `socket_timeout=2`, и
        тест остаётся зелёным на «слепом» исправлении — то есть гейт молча не
        проверяет ничего. Блокирующий `listen()` ведёт себя иначе, и только он
        воспроизводит прод-режим.
        """
        pubsub, client = await rp.subscribe_to_requests()
        received: list[str] = []

        async def pump():
            async for message in pubsub.listen():
                if message.get("type") == "message":
                    received.append(message["data"])
                    return

        task = asyncio.create_task(pump())
        try:
            # Тишина заведомо дольше любого разумного операционного таймаута.
            await asyncio.sleep(3.5)
            assert not task.done(), (
                "подписка порвалась за время тишины — операционный таймаут на "
                f"подписчике? (исключение: {task.exception() if task.done() else None})"
            )

            await rp.publish_request_event("quiet.test", {"ok": True})
            await asyncio.wait_for(task, timeout=10)

            assert received and "quiet.test" in received[0]
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            await pubsub.unsubscribe()
            await client.aclose()
