"""Видеоинструкции жителя в боте (решение владельца 2026-11-04).

Ролик «как зарегистрироваться» — один раз при выборе «Я житель»; «как подать
заявку» — один раз после получения доступа (кнопка «Перезапустить бота» или
первый /start) и после >3 свободных сообщений за сутки (не чаще раза в 7 дней);
оба — кнопками в «Помощи».
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import FSInputFile

from uk_management_bot.handlers import base, start_role_choice
from uk_management_bot.services import tutorial_videos as tv
from uk_management_bot.utils.helpers import get_text


class FakeRedis:
    def __init__(self):
        self.store: dict[str, object] = {}
        self.ttl: dict[str, int] = {}

    async def get(self, key):
        return self.store.get(key)

    async def set(self, key, value, nx=False, ex=None):
        if nx and key in self.store:
            return None
        self.store[key] = value
        if ex:
            self.ttl[key] = ex
        return True

    async def incr(self, key):
        self.store[key] = int(self.store.get(key, 0)) + 1
        return self.store[key]

    async def expire(self, key, seconds):
        self.ttl[key] = seconds

    async def delete(self, key):
        self.store.pop(key, None)


@pytest.fixture()
def redis(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(tv, "_get_redis", AsyncMock(return_value=fake))
    return fake


def _bot(file_id="FID-1"):
    bot = MagicMock()
    bot.send_video = AsyncMock(return_value=SimpleNamespace(video=SimpleNamespace(file_id=file_id)))
    return bot


async def _drain():
    """Дождаться фоновых роликов (tutorial_videos.schedule)."""
    loop = asyncio.get_running_loop()
    while mine := [t for t in tv._BACKGROUND if t.get_loop() is loop and not t.done()]:
        await asyncio.gather(*mine)


def _sent_media(bot, call=-1):
    return bot.send_video.await_args_list[call].args[1]


# ───────────────────────── модуль ─────────────────────────


def test_every_kind_and_language_has_a_video_file():
    for kind in tv.KINDS:
        for lang in ("ru", "uz"):
            assert tv.video_path(kind, lang).is_file(), (kind, lang)


def test_uz_cyrl_uses_uzbek_video_and_unknown_uses_russian():
    assert tv.video_path("request", "uz_cyrl").name == "request_uz.mp4"
    assert tv.video_path("request", None).name == "request_ru.mp4"
    assert tv.video_path("request", "en").name == "request_ru.mp4"


@pytest.mark.asyncio
@pytest.mark.parametrize("lang", ["ru", "uz"])
async def test_first_send_uploads_file_then_reuses_file_id(redis, lang):
    bot = _bot()
    assert await tv.send_tutorial(bot, 42, "request", lang)
    assert isinstance(_sent_media(bot), FSInputFile)
    caption = bot.send_video.await_args.kwargs["caption"]
    assert caption == get_text("tutorial.request.caption", language=lang) != "tutorial.request.caption"

    assert await tv.send_tutorial(bot, 43, "request", lang)
    assert _sent_media(bot) == "FID-1"


@pytest.mark.asyncio
async def test_stale_file_id_is_reuploaded(redis):
    bot = _bot()
    await tv.send_tutorial(bot, 42, "registration", "ru")
    bot.send_video = AsyncMock(side_effect=[
        TelegramBadRequest(method=MagicMock(), message="wrong file identifier"),
        SimpleNamespace(video=SimpleNamespace(file_id="FID-2")),
    ])
    assert await tv.send_tutorial(bot, 42, "registration", "ru")
    assert isinstance(_sent_media(bot), FSInputFile)
    assert "FID-2" in redis.store.values()


@pytest.mark.asyncio
async def test_send_failure_is_swallowed(redis):
    bot = MagicMock()
    bot.send_video = AsyncMock(side_effect=RuntimeError("network"))
    assert await tv.send_tutorial(bot, 42, "request", "ru") is False


@pytest.mark.asyncio
async def test_help_button_works_without_redis(monkeypatch):
    monkeypatch.setattr(tv, "_get_redis", AsyncMock(side_effect=ConnectionError))
    bot = _bot()
    assert await tv.send_tutorial(bot, 42, "request", "ru")
    bot.send_video.assert_awaited_once()


@pytest.mark.asyncio
async def test_send_once_sends_only_first_time(redis):
    bot = _bot()
    assert await tv.send_tutorial_once(bot, 7, "registration", "ru", ttl=100)
    assert not await tv.send_tutorial_once(bot, 7, "registration", "ru", ttl=100)
    assert bot.send_video.await_count == 1
    assert redis.ttl["tutorial:sent:registration:7"] == 100


@pytest.mark.asyncio
async def test_send_once_skips_without_redis(monkeypatch):
    """Без Redis автоматический показ молчит: иначе ролик на каждый /start."""
    monkeypatch.setattr(tv, "_get_redis", AsyncMock(side_effect=ConnectionError))
    bot = _bot()
    assert not await tv.send_tutorial_once(bot, 7, "request", "ru", ttl=100)
    bot.send_video.assert_not_awaited()


@pytest.mark.asyncio
async def test_free_text_offer_on_fourth_message_then_weekly(redis):
    bot = _bot()
    results = [await tv.offer_after_free_text(bot, 9, "uz") for _ in range(5)]
    assert results == [False, False, False, True, False]
    assert bot.send_video.await_args.kwargs["caption"] == get_text("tutorial.free_text_offer", language="uz")
    assert redis.ttl["tutorial:free:9"] == tv.FREE_TEXT_WINDOW
    assert redis.ttl["tutorial:sent:free_text:9"] == tv.FREE_TEXT_OFFER_TTL


@pytest.mark.asyncio
async def test_free_text_offer_independent_of_approval_flag(redis):
    bot = _bot()
    await tv.send_tutorial_once(bot, 9, "request", "ru", ttl=tv.REQUEST_ONCE_TTL)
    for _ in range(4):
        await tv.offer_after_free_text(bot, 9, "ru")
    assert bot.send_video.await_count == 2


# ───────────────────────── хендлеры ─────────────────────────


def _ctx(status="approved", roles=("applicant",), phone="+998900000001", verification="verified"):
    return base._MenuContext(
        status=status, phone=phone, has_approved_apartment=True, has_any_apartment=True,
        db_roles=list(roles), active_role=roles[0], has_property_doc=True, verification_status=verification,
    )


@pytest.mark.parametrize("ctx, expected", [
    (_ctx(), True),
    (_ctx(status="pending"), False),
    (_ctx(verification="pending"), False),
    (_ctx(phone=None), False),
    (_ctx(roles=("applicant", "executor")), False),
])
def test_resident_access_predicate(ctx, expected):
    assert base._has_resident_access(ctx) is expected


def _callback(data="restart_bot", user_id=555):
    cb = MagicMock()
    cb.data = data
    cb.from_user.id = user_id
    cb.message.chat.id = user_id
    cb.message.answer = AsyncMock()
    cb.answer = AsyncMock()
    cb.bot = _bot()
    cb.message.bot = cb.bot
    return cb


@pytest.mark.asyncio
@pytest.mark.parametrize("status, sent", [("approved", True), ("pending", False)])
async def test_restart_bot_sends_request_video_once_to_resident(redis, status, sent):
    cb = _callback()
    with patch.object(base, "run_db", AsyncMock(return_value=_ctx(status=status))):
        await base.handle_restart_bot(cb, language="ru")
        await _drain()
        await base.handle_restart_bot(cb, language="ru")
        await _drain()
    assert cb.bot.send_video.await_count == (1 if sent else 0)
    if sent:
        assert cb.bot.send_video.await_args.args[0] == 555


@pytest.mark.asyncio
async def test_choose_resident_sends_registration_video_once(redis):
    cb = _callback(data="start_role:resident")
    state = MagicMock(clear=AsyncMock())
    with patch.object(start_role_choice, "send_onboarding_screen", AsyncMock()), \
            patch.object(start_role_choice, "_strip_markup", AsyncMock()):
        await start_role_choice.choose_resident(cb, state, language="uz")
        await _drain()
        await start_role_choice.choose_resident(cb, state, language="uz")
        await _drain()
    cb.bot.send_video.assert_awaited_once()
    assert tv.video_path("registration", "uz").name in str(_sent_media(cb.bot).path)


@pytest.mark.asyncio
async def test_help_shows_both_tutorial_buttons():
    msg = MagicMock()
    msg.from_user.id = 1
    msg.answer = AsyncMock()
    with patch.object(base, "run_db", AsyncMock(return_value="uz")):
        await base.show_help(msg)
    markup = msg.answer.await_args.kwargs["reply_markup"]
    buttons = [b for row in markup.inline_keyboard for b in row]
    assert [b.callback_data for b in buttons] == ["tutorial:registration", "tutorial:request"]
    assert buttons[1].text == get_text("tutorial.btn_request", language="uz")


@pytest.mark.asyncio
async def test_help_callback_sends_video_and_ignores_unknown_kind(redis):
    cb = _callback(data="tutorial:request")
    await base.send_tutorial_video(cb, language="ru")
    cb.bot.send_video.assert_awaited_once()
    cb2 = _callback(data="tutorial:../../etc")
    await base.send_tutorial_video(cb2, language="ru")
    cb2.bot.send_video.assert_not_awaited()
    cb2.answer.assert_awaited()


def _msg(user_id=777):
    msg = MagicMock()
    msg.text = "течёт кран"
    msg.from_user.id = user_id
    msg.answer = AsyncMock()
    msg.bot = _bot()
    return msg


@pytest.mark.asyncio
@pytest.mark.parametrize("status, roles, sent", [
    ("approved", ["applicant"], True),
    ("pending", ["applicant"], False),
    ("approved", ["executor"], False),
])
async def test_free_text_handler_offers_video_only_to_approved_resident(redis, status, roles, sent):
    msg = _msg()
    with patch.object(base, "get_user_contextual_keyboard", AsyncMock(return_value=None)):
        for _ in range(4):
            await base.free_text_request_hint(msg, user_status=status, language="ru", roles=roles)
            await _drain()
    assert msg.answer.await_count == 4  # подсказка — на каждое сообщение
    assert msg.bot.send_video.await_count == (1 if sent else 0)


@pytest.mark.parametrize("data", ["tutorial:registration", "tutorial:request"])
def test_routing_help_buttons_reach_tutorial_handler(data):
    """Реальная цепочка роутеров main.py: колбэк не перехватывает чужой catch-all."""
    import re
    from pathlib import Path

    import uk_management_bot.main as main_mod
    from uk_management_bot.tests.handlers.routing_probe import make_callback, resolve_ctx

    order = re.findall(r"dp\.include_router\((\w+)\)", Path(main_mod.__file__).read_text())
    routers = [getattr(main_mod, name) for name in order]
    assert resolve_ctx(routers, make_callback(data), "callback_query", roles=["applicant"], user=None) == (
        "uk_management_bot.handlers.base", "send_tutorial_video")


# ───────────────────── исправления по ревью 2026-11-04 ─────────────────────


@pytest.mark.asyncio
async def test_failed_send_releases_flag_so_next_trigger_retries(redis):
    """Дев-ревью HIGH-1: флаг ставился до отправки — сбой «сжигал» ролик на год."""
    bot = _bot()
    bot.send_video = AsyncMock(side_effect=[
        RuntimeError("network"),
        SimpleNamespace(video=SimpleNamespace(file_id="FID-1")),
    ])
    assert not await tv.send_tutorial_once(bot, 7, "request", "ru", ttl=tv.REQUEST_ONCE_TTL)
    assert "tutorial:sent:request:7" not in redis.store
    assert await tv.send_tutorial_once(bot, 7, "request", "ru", ttl=tv.REQUEST_ONCE_TTL)
    assert redis.store["tutorial:sent:request:7"] == "1"


@pytest.mark.asyncio
async def test_handler_does_not_wait_for_video(redis):
    """Дев-ревью HIGH-2: ролик — после ответа и в фоне, хендлер его не ждёт."""
    cb = _callback()
    gate = asyncio.Event()

    async def slow_send(*args, **kwargs):
        await gate.wait()
        return SimpleNamespace(video=SimpleNamespace(file_id="FID-1"))

    cb.bot.send_video = AsyncMock(side_effect=slow_send)
    with patch.object(base, "run_db", AsyncMock(return_value=_ctx())):
        await asyncio.wait_for(base.handle_restart_bot(cb, language="ru"), timeout=1)
    cb.message.answer.assert_awaited_once()  # меню уже отправлено
    assert any(not t.done() for t in tv._BACKGROUND)  # ролик ещё в пути
    gate.set()
    await _drain()
    cb.bot.send_video.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("ctx, sent", [
    (_ctx(), True),
    (_ctx(roles=("executor", "applicant")), False),
    (_ctx(status="blocked"), False),
])
async def test_regular_start_offers_request_video_to_resident_with_access(redis, ctx, sent):
    msg = _msg(user_id=888)
    with patch.object(base, "run_db", AsyncMock(return_value=ctx)):
        await base.handle_regular_start(msg, language="ru")
        await _drain()
        await base.handle_regular_start(msg, language="ru")
        await _drain()
    assert msg.bot.send_video.await_count == (1 if sent else 0)


@pytest.mark.asyncio
async def test_help_button_cooldown(redis):
    """Сек-ревью MEDIUM: кнопку можно жать скриптом — не чаще ролика в 10 с."""
    cb = _callback(data="tutorial:request")
    for _ in range(5):
        await base.send_tutorial_video(cb, language="ru")
    cb.bot.send_video.assert_awaited_once()
    assert cb.answer.await_count == 5  # нажатие всё равно подтверждаем
    assert redis.ttl["tutorial:cd:request:555"] == tv.HELP_COOLDOWN
    # Другой ролик сразу следом — не блокируется (живой прогон 2026-11-04).
    cb.data = "tutorial:registration"
    await base.send_tutorial_video(cb, language="ru")
    assert cb.bot.send_video.await_count == 2


@pytest.mark.asyncio
async def test_free_text_counter_gets_ttl_on_creation(redis):
    """Дев-ревью MEDIUM: срок ставится вместе с ключом, не отдельным EXPIRE."""
    assert await tv.count_free_text(5) == 1
    assert redis.ttl["tutorial:free:5"] == tv.FREE_TEXT_WINDOW
    redis.ttl.clear()
    assert await tv.count_free_text(5) == 2
    assert "tutorial:free:5" not in redis.ttl  # повторно срок не трогаем
