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


def test_reply_mock_shape_matches_handler_contract():
    """Страховка харнесса: reply — AsyncMock, иначе assert_awaited не имеет смысла."""
    message = make_message()
    assert isinstance(message.reply, AsyncMock)
