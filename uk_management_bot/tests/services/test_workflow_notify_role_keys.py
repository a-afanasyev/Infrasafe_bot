"""Ролевые ключи notify-матрицы: наряд исполнителю ≠ статус жителю.

Дефект, который здесь пинится: ключ `notifications.workflow.assigned` написан
ДЛЯ ЖИТЕЛЯ («заявка принята в работу»), а матрица слала его обоим получателям.
Исполнитель, которому только что дали работу, получал чужую статусную строку
без категории, описания и призыва — то есть наряд, по которому нельзя выйти.

Проверяется не только сам факт разных ключей, но и механика: одна спецификация
на действие не позволяет выбрать текст по роли, потому что `_wanted_user_ids`
схлопывает роли в множество id и теряет, по какой роли выбран человек.
"""
import html
from types import SimpleNamespace

import pytest

from uk_management_bot.services.workflow_notifications import (
    APPLICANT,
    EXECUTOR,
    _NOTIFY_MATRIX,
    _plan,
    _render_text,
    _resolve_targets,
    _specs,
)
from uk_management_bot.utils.helpers import get_text
from uk_management_bot.utils.request_workflow import Action

ASSIGN_ACTIONS = [Action.MANAGER_ASSIGN, Action.SYSTEM_DISPATCH_ASSIGN]


def _intent(action: Action):
    return SimpleNamespace(kind="notify", data={"action": action.value})


def _request(*, user_id=11, executor_id=22, category="plumbing",
             address="ул. Тестовая, 1", description="течёт кран"):
    return SimpleNamespace(
        request_number="260819-001",
        user_id=user_id,
        executor_id=executor_id,
        category=category,
        address=address,
        description=description,
    )


# ─────────────────────────── структура матрицы ───────────────────────────


@pytest.mark.parametrize("action", ASSIGN_ACTIONS)
def test_assign_actions_carry_two_specs(action):
    specs = _specs(_NOTIFY_MATRIX[action])
    assert len(specs) == 2, "жителю и исполнителю нужны РАЗНЫЕ тексты"

    by_role = {roles: key for roles, key in specs}
    assert by_role[(EXECUTOR,)] == "notifications.workflow.assigned_executor"
    assert by_role[(APPLICANT,)] == "notifications.workflow.assigned"


@pytest.mark.parametrize("action", ASSIGN_ACTIONS)
def test_executor_spec_comes_first_for_dedup_priority(action):
    """Дедуп берёт ПЕРВОЕ задание; исполнительский текст богаче жительского."""
    first_roles, _ = _specs(_NOTIFY_MATRIX[action])[0]
    assert first_roles == (EXECUTOR,)


def test_single_spec_actions_are_not_broken_by_normalization():
    """Историческая форма `((role,), "key")` обязана пережить разворачивание."""
    specs = _specs(_NOTIFY_MATRIX[Action.CANCEL])
    assert specs == (((APPLICANT,), "notifications.workflow.cancelled"),)


# ─────────────────────────── разворачивание плана ───────────────────────────


@pytest.mark.parametrize("action", ASSIGN_ACTIONS)
def test_plan_expands_assign_into_two_jobs(action):
    plan = _plan([_intent(action)])
    assert len(plan) == 2
    assert {key for _, _, key in plan} == {
        "notifications.workflow.assigned",
        "notifications.workflow.assigned_executor",
    }


def test_plan_keeps_one_job_for_single_spec_action():
    assert len(_plan([_intent(Action.CANCEL)])) == 1


@pytest.mark.parametrize("action", ASSIGN_ACTIONS)
def test_targets_route_each_role_to_its_own_key(action):
    request = _request(user_id=11, executor_id=22)
    targets = _resolve_targets(request, _plan([_intent(action)]))

    by_key = {key: ids for _, key, ids in targets}
    assert by_key["notifications.workflow.assigned_executor"] == {22}
    assert by_key["notifications.workflow.assigned"] == {11}


@pytest.mark.parametrize("action", ASSIGN_ACTIONS)
def test_same_person_as_applicant_and_executor_gets_one_message(action):
    """Житель, назначенный исполнителем СВОЕЙ заявки, не должен получить два
    сообщения об одном событии. Побеждает наряд — он содержит всё, что есть в
    жительском тексте, плюс детали работы."""
    request = _request(user_id=7, executor_id=7)
    targets = _resolve_targets(request, _plan([_intent(action)]))

    delivered = [(key, ids) for _, key, ids in targets if ids]
    assert delivered == [("notifications.workflow.assigned_executor", {7})]


def test_dedup_is_per_action_not_global():
    """Два разных перехода в одной пачке — законный повод написать дважды."""
    request = _request(user_id=11, executor_id=22)
    plan = _plan([_intent(Action.MANAGER_ASSIGN), _intent(Action.CANCEL)])
    targets = _resolve_targets(request, plan)

    applicant_hits = [key for _, key, ids in targets if 11 in ids]
    assert sorted(applicant_hits) == [
        "notifications.workflow.assigned",
        "notifications.workflow.cancelled",
    ]


# ─────────────────────────── рендер наряда ───────────────────────────


@pytest.mark.parametrize("language", ["ru", "uz"])
def test_assigned_executor_template_exists_in_both_locales(language):
    template = get_text("notifications.workflow.assigned_executor", language=language)
    assert template != "notifications.workflow.assigned_executor", "ключ отсутствует"
    for placeholder in ("{request_number}", "{category}", "{address}", "{description}"):
        assert placeholder in template, placeholder


@pytest.mark.parametrize("language", ["ru", "uz"])
def test_reassigned_away_template_exists_in_both_locales(language):
    template = get_text("notifications.workflow.reassigned_away", language=language)
    assert template != "notifications.workflow.reassigned_away", "ключ отсутствует"
    assert "{request_number}" in template


def test_assigned_executor_render_localizes_category():
    text = _render_text(
        Action.MANAGER_ASSIGN, "notifications.workflow.assigned_executor",
        "ru", _request(category="plumbing"), None,
    )
    assert "plumbing" not in text, "категория обязана быть локализована"


def test_assigned_executor_render_escapes_free_text():
    request = _request(address="ул. <b>Х</b> & 1", description="<script>alert(1)</script>")
    text = _render_text(
        Action.MANAGER_ASSIGN, "notifications.workflow.assigned_executor",
        "ru", request, None,
    )
    assert "<script>" not in text
    assert html.escape("<script>alert(1)</script>") in text
    assert "&amp;" in text


def test_assigned_executor_render_clips_long_description():
    """Обрезка ДО escape: резать после — рвать entity пополам."""
    request = _request(description="я" * 5000, address="а" * 5000)
    text = _render_text(
        Action.MANAGER_ASSIGN, "notifications.workflow.assigned_executor",
        "ru", request, None,
    )
    assert len(text) < 1000, "длинное описание дало бы MESSAGE_TOO_LONG"
    assert "..." in text


def test_assigned_executor_render_survives_empty_fields():
    request = _request(address=None, description=None)
    text = _render_text(
        Action.MANAGER_ASSIGN, "notifications.workflow.assigned_executor",
        "ru", request, None,
    )
    assert "260819-001" in text


def test_applicant_key_still_renders_without_description_placeholder():
    """Жительский текст не изменился — у него нет ни категории-наряда, ни описания."""
    text = _render_text(
        Action.MANAGER_ASSIGN, "notifications.workflow.assigned",
        "ru", _request(), None,
    )
    assert "течёт кран" not in text
