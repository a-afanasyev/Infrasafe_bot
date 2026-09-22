# ruff: noqa: F811 — фикстуры env/db импортированы из staff-модуля и переданы как параметры
"""Тег-режим Group Intake: кириллический тег и поведение при сбое классификатора.

Живой инцидент 2026-09-22 (profk, «Заявки по Олмазар сити»): сотрудники пишут
``#ариза`` кириллицей — бот знал только ``#заявка``/``#ariza`` и молча ронял
сообщения; единственное распознанное сообщение за сутки добил разовый таймаут
Anthropic, а PROCESSING_ERROR в тег-режиме = тишина без ответа автору.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import uk_management_bot.handlers.group_intake as gi
from uk_management_bot.services.group_intake.classifier import (
    ClassificationResult,
    Outcome,
)
from uk_management_bot.tests.handlers.test_group_intake_staff import (  # noqa: F401
    db,
    env,
    make_message,
    run_entry,
    seed_directory,
    seed_staff_group,
    seed_staff_user,
)
from uk_management_bot.utils.helpers import get_text

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize("tag", ["#ариза", "#Ариза", "#АРИЗА", "#zayavka", "#Zayavka"])
async def test_cyrillic_and_translit_tags_run_pipeline(env, db, tag):
    """``#ариза``/``#zayavka`` — такие же явные маркеры, как ``#заявка``/``#ariza``."""
    seed_staff_group(db, require_tag=True)
    seed_staff_user(db)
    seed_directory(db)
    message = make_message(text=f"{tag} у дома 12 отвалилась плитка, опасно")
    await run_entry(message, db)
    env.classify.assert_awaited_once()
    message.reply.assert_awaited_once()
    assert "#" not in env.classify.await_args.args[0]
    payload = env.store_candidate.await_args.args[2]
    assert "#" not in payload["text"]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("#ариза нет света в подъезде", "нет света в подъезде"),
        ("Нет воды #ЗАЯВКА дом 5", "Нет воды дом 5"),
        ("#zayavka lift ishlamayapti", "lift ishlamayapti"),
        ("нет света", None),
    ],
)
def test_strip_request_tag_variants(text, expected):
    assert gi.strip_request_tag(text) == expected


async def test_tag_mode_classifier_error_replies_to_author(env, db):
    """Тег = явное намерение: сломанный классификатор не должен быть тишиной —
    автор получает просьбу повторить, кандидат не создаётся."""
    seed_staff_group(db, require_tag=True)
    seed_staff_user(db)
    seed_directory(db)
    env.classify.return_value = ClassificationResult(outcome=Outcome.PROCESSING_ERROR)
    message = make_message(text="#ариза у дома 12 отвалилась плитка, опасно")
    await run_entry(message, db)
    env.classify.assert_awaited_once()
    message.reply.assert_awaited_once_with(
        get_text("group_intake.classifier_unavailable", language="ru")
    )
    env.store_candidate.assert_not_awaited()


async def test_tag_mode_classifier_error_reply_is_localized(env, db):
    seed_staff_group(db, require_tag=True)
    seed_staff_user(db)
    seed_directory(db)
    env.classify.return_value = ClassificationResult(outcome=Outcome.PROCESSING_ERROR)
    message = make_message(text="#ariza 12-uyda plitka tushib ketdi, xavfli")
    message.from_user = SimpleNamespace(id=message.from_user.id, is_bot=False, language_code="uz")
    await run_entry(message, db)
    text = message.reply.await_args.args[0]
    assert text == get_text("group_intake.classifier_unavailable", language="uz")
    assert text != "group_intake.classifier_unavailable"


async def test_no_tag_mode_classifier_error_stays_silent(env, db):
    """Без тега намерение не выражено — прежняя тишина (никакого спама в группе)."""
    seed_staff_group(db, require_tag=False)
    seed_staff_user(db)
    seed_directory(db)
    env.classify.return_value = ClassificationResult(outcome=Outcome.PROCESSING_ERROR)
    message = make_message(text="У дома 12 отвалилась плитка, опасно для прохожих")
    await run_entry(message, db)
    env.classify.assert_awaited_once()
    message.reply.assert_not_awaited()


def test_locale_key_present_in_both_languages():
    for lang in ("ru", "uz"):
        assert get_text("group_intake.classifier_unavailable", language=lang) != (
            "group_intake.classifier_unavailable"
        )


# ───────────── A9-P2-6: отказ лимитера в тег-режиме — не тишина ─────────────


@pytest.fixture()
def busy(monkeypatch, env):
    """Лимитер отказал; снятие seen и cooldown ответа — наблюдаемые моки."""
    env.llm_allowed.return_value = False
    mocks = SimpleNamespace(
        unmark_seen=AsyncMock(),
        busy_notice_allowed=AsyncMock(return_value=True),
    )
    monkeypatch.setattr(gi.pending, "unmark_seen", mocks.unmark_seen, raising=False)
    monkeypatch.setattr(
        gi.pending, "busy_notice_allowed", mocks.busy_notice_allowed, raising=False
    )
    return mocks


async def test_tag_mode_rate_limited_replies_and_releases_seen(env, db, busy):
    seed_staff_group(db, require_tag=True)
    seed_staff_user(db)
    seed_directory(db)
    message = make_message(text="#ариза у дома 12 отвалилась плитка, опасно")
    await run_entry(message, db)
    env.classify.assert_not_awaited()
    message.reply.assert_awaited_once_with(
        get_text("group_intake.classifier_unavailable", language="ru")
    )
    # повтор автора того же сообщения (правка/пересылка) не должен стать «дублем»
    busy.unmark_seen.assert_awaited_once_with(message.chat.id, message.message_id)
    busy.busy_notice_allowed.assert_awaited_once_with(message.chat.id, message.from_user.id)


async def test_tag_mode_rate_limited_notice_respects_cooldown(env, db, busy):
    busy.busy_notice_allowed.return_value = False
    seed_staff_group(db, require_tag=True)
    seed_staff_user(db)
    seed_directory(db)
    message = make_message(text="#ариза у дома 12 отвалилась плитка, опасно")
    await run_entry(message, db)
    message.reply.assert_not_awaited()
    busy.unmark_seen.assert_awaited_once()


async def test_no_tag_mode_rate_limited_stays_silent(env, db, busy):
    seed_staff_group(db, require_tag=False)
    seed_staff_user(db)
    seed_directory(db)
    message = make_message(text="У дома 12 отвалилась плитка, опасно для прохожих")
    await run_entry(message, db)
    message.reply.assert_not_awaited()
    busy.busy_notice_allowed.assert_not_awaited()


async def test_llm_retry_goes_through_group_limiter(env, db):
    """A9-P3-7: повтор вызова LLM — через тот же лимитер группы."""
    seed_staff_group(db, require_tag=True)
    seed_staff_user(db)
    seed_directory(db)
    message = make_message(text="#ариза у дома 12 отвалилась плитка, опасно")
    await run_entry(message, db)
    gate = env.classify.await_args.kwargs["retry_allowed"]
    assert env.llm_allowed.await_count == 1
    await gate()
    assert env.llm_allowed.await_count == 2
    env.llm_allowed.assert_awaited_with(message.chat.id)


# ───────────── A9-P3-6: staff-гейт до «тег + видео», теги целым словом ─────────────


async def test_tagged_video_from_outsider_in_staff_group_is_silent(env, db):
    """«Полная тишина» для чужих в служебном чате — и с тегом, и с видео."""
    seed_staff_group(db, require_tag=True)
    message = make_message(
        text=None, caption="#заявка у дома 12 прорвало трубу, вода хлещет",
        video=SimpleNamespace(file_id="vid1"),
        from_id=999_999,
    )
    await run_entry(message, db)
    message.reply.assert_not_awaited()
    env.classify.assert_not_awaited()


async def test_tagged_video_from_staff_uses_profile_language(env, db):
    seed_staff_group(db, require_tag=True)
    user = seed_staff_user(db)
    user.language = "uz"
    db.commit()
    message = make_message(
        text=None, caption="#ariza 12-uyda quvur yorildi",
        video=SimpleNamespace(file_id="vid1"),
    )
    await run_entry(message, db)
    message.reply.assert_awaited_once_with(get_text("group_intake.photo_only", language="uz"))


@pytest.mark.parametrize(
    "text",
    [
        "#заявкам нет света в подъезде",
        "#arizalar lift ishlamayapti",
        "пишу#заявка нет света",
        "#ариза_2 нет воды",
    ],
)
def test_tag_must_be_whole_word(text):
    assert gi.strip_request_tag(text) is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("#заявка, нет света", ", нет света"),
        ("нет света (#ariza)", "нет света ( )"),
        ("Нет воды.#ЗАЯВКА", "Нет воды."),
    ],
)
def test_tag_word_boundary_accepts_punctuation(text, expected):
    assert gi.strip_request_tag(text) == expected


async def test_tagged_not_request_without_keyword_is_default_source(env, db):
    """Фолбэк в «Другое» — не вердикт модели: источник `default`, не `llm`."""
    seed_staff_group(db, require_tag=True)
    seed_staff_user(db)
    seed_directory(db)
    env.classify.return_value = ClassificationResult(outcome=Outcome.NOT_REQUEST)
    message = make_message(text="#заявка посмотрите у дома 12 пожалуйста")
    await run_entry(message, db)
    payload = env.store_candidate.await_args.args[2]
    assert payload["category"] == "other"
    assert payload["category_source"] == "default"


def test_reply_mock_shape_matches_handler_contract():
    """Страховка харнесса: reply — AsyncMock, иначе assert_awaited не имеет смысла."""
    message = make_message()
    assert isinstance(message.reply, AsyncMock)
