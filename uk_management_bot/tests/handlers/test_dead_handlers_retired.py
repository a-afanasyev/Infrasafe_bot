"""Ретайр мёртвых хендлеров бота: BUG-150 + BUG-154 + BUG-158 (2026-08-19).

Пин РЕТАЙРА, а не поведения: каждый удалённый триггер обязан не разрешаться
НИКУДА — ни для жителя, ни для менеджера. Проверяется через `resolve_ctx` на
реальном списке роутеров в порядке `main.py` (порядок ИЗВЛЕКАЕТСЯ из исходника,
не копируется), потому что «удалил функцию» и «закрыл вход» — разные вещи:
`callback_data` присылает КЛИЕНТ, и пока цепочка роутеров кого-то находит,
вход живой (урок BUG-155/169).

Обратная половина пина не менее важна: живые соседи по тем же префиксам обязаны
разрешаться туда же, куда и до ретайра. Ретайр, забравший живой флоу в тишину,
хуже незакрытого мёртвого кода.

⚠️ Мина `executor_*` (BUG-154, наблюдение ревьюера) — подтверждена живой пробой
до ретайра: единственный генератор БАРЕ `executor_<id>` — клавиатура самого
мёртвого кластера, но фильтр `startswith("executor_")` в `request_assignment`
(main.py:384) ловил ВСЁ, что не забрали роутеры выше. Живой `executor_assignment`
от менеджера уходил в `shift_management` (роутер 370), а от исполнителя —
проваливался в мёртвый хендлер, потому что RoleGate пакета смен отказывает
исполнителю и апдейт идёт дальше по цепочке. После ретайра — тишина, как и
должно быть.

Победитель везде сверяется ПАРОЙ (module, name): имена хендлеров в проекте
дублируются.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

import uk_management_bot.main as main_mod
from uk_management_bot.tests.handlers.routing_probe import (
    make_callback,
    make_message,
    resolve_ctx,
)
from uk_management_bot.utils.button_texts import (
    get_active_shifts_button_texts,
    get_specify_address_texts,
)

# Порядок роутеров — из САМОГО main.py (SSOT), не копия: удаление
# include_router подхватывается автоматически.
_ORDER = re.findall(r"dp\.include_router\((\w+)\)", Path(main_mod.__file__).read_text())
ROUTERS = [getattr(main_mod, name) for name in _ORDER]

H = "uk_management_bot.handlers"
REQUEST_NUMBER = "260814-001"

APPLICANT = {"roles": ["applicant"], "user": None}
EXECUTOR = {"roles": ["executor"], "user": None}
MANAGER = {"roles": ["manager"], "user": None}


def _cb(data: str, **ctx):
    return resolve_ctx(ROUTERS, make_callback(data), "callback_query", **ctx)


def _msg(text: str, **ctx):
    return resolve_ctx(ROUTERS, make_message(text), "message", **ctx)


# ══════════════════════════════════════════════════════════════════════════════
# Ретайренные callback-входы: НИКТО не отвечает, ни жителю, ни менеджеру
# ══════════════════════════════════════════════════════════════════════════════

RETIRED_CALLBACKS = [
    # BUG-150
    pytest.param(f"back_to_report_{REQUEST_NUMBER}", id="bug150-back_to_report(дыра P1)"),
    pytest.param("shift_end_confirm_yes", id="bug150-bare-shift_end_confirm_yes"),
    pytest.param("shift_end_confirm_no", id="bug150-shift_end_confirm_no"),
    pytest.param("force_end_shift_1", id="bug150-force_end_shift"),
    # BUG-154 — кластер request_assignment целиком
    pytest.param(f"assign_request_{REQUEST_NUMBER}", id="bug154-assign_request(вход цепочки)"),
    pytest.param("assign_group_1", id="bug154-assign_group"),
    pytest.param("assign_individual_1", id="bug154-assign_individual"),
    pytest.param("specialization_plumber", id="bug154-specialization"),
    pytest.param("confirm_assignment", id="bug154-confirm_assignment"),
    pytest.param("cancel_assignment", id="bug154-cancel_assignment"),
    pytest.param(f"view_assignments_{REQUEST_NUMBER}", id="bug154-view_assignments"),
    pytest.param("executor_1", id="bug154-bare-executor_id"),
    # BUG-154 — panels
    pytest.param("quick_verify_1", id="bug154-quick_verify"),
    pytest.param("quick_reject_1", id="bug154-quick_reject"),
    pytest.param("user_mgmt_stats_with_verification", id="bug154-stats_with_verification"),
]


@pytest.mark.parametrize("data", RETIRED_CALLBACKS)
@pytest.mark.parametrize("ctx,who", [(APPLICANT, "applicant"), (MANAGER, "manager")])
def test_retired_callback_resolves_nowhere(data, ctx, who):
    """Ретайр закрывает вход для ВСЕХ ролей, а не перевешивает его на другого."""
    assert _cb(data, **ctx) is None, f"{data} всё ещё разрешается для {who}"


# ══════════════════════════════════════════════════════════════════════════════
# Ретайренные message-входы
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("text", sorted(get_active_shifts_button_texts()))
@pytest.mark.parametrize("ctx,who", [(APPLICANT, "applicant"), (MANAGER, "manager")])
def test_retired_active_shifts_button_resolves_nowhere(text, ctx, who):
    """BUG-150 `manager_active_shifts`: текст кнопки не рендерила ни одна
    клавиатура, но message-хендлер ловил его у любого, кто ВВЕДЁТ текст руками."""
    assert _msg(text, **ctx) is None, f"{text!r} всё ещё разрешается для {who}"


@pytest.mark.parametrize("text", sorted(get_specify_address_texts()))
@pytest.mark.parametrize("ctx,who", [(APPLICANT, "applicant"), (MANAGER, "manager")])
def test_retired_specify_address_button_resolves_nowhere(text, ctx, who):
    """BUG-158 `start_address_input`: LEGACY-текст, генератора нет нигде."""
    assert _msg(text, **ctx) is None, f"{text!r} всё ещё разрешается для {who}"


# ══════════════════════════════════════════════════════════════════════════════
# Мина executor_* снята (BUG-154)
# ══════════════════════════════════════════════════════════════════════════════


def test_executor_assignment_back_still_reaches_shift_management():
    """Живой «Назад» в UI назначения смен остаётся у менеджера на своём месте."""
    assert _cb("executor_assignment", **MANAGER) == (
        f"{H}.shift_management.assignment_b", "handle_executor_assignment_back"
    )


def test_executor_assignment_from_executor_is_silent_not_swallowed():
    """До ретайра исполнитель проваливался в мёртвый `handle_executor_selection`
    (RoleGate пакета смен отказывает, апдейт идёт дальше). После — тишина."""
    assert _cb("executor_assignment", **EXECUTOR) is None


# ══════════════════════════════════════════════════════════════════════════════
# Живые соседи по тем же префиксам — не задеты
# ══════════════════════════════════════════════════════════════════════════════

LIVE_NEIGHBOURS = [
    (f"view_report_{REQUEST_NUMBER}", f"{H}.request_reports", "handle_view_report", MANAGER),
    ("end_shift_select:1", f"{H}.shifts", "handle_shift_selection", EXECUTOR),
    ("shift_end_confirm_yes:1", f"{H}.shifts", "end_shift_yes_with_id", EXECUTOR),
    ("suggest_executor_skip", f"{H}.shifts", "suggest_executor_skip", EXECUTOR),
    (f"executor_complete_{REQUEST_NUMBER}", f"{H}.requests.executor", "executor_complete_request", EXECUTOR),
    (f"executor_purchase_{REQUEST_NUMBER}", f"{H}.requests.executor", "executor_request_purchase", EXECUTOR),
    (f"executor_work_{REQUEST_NUMBER}", f"{H}.requests.executor", "executor_return_to_work", EXECUTOR),
    (f"executor_view_media_{REQUEST_NUMBER}", f"{H}.requests.executor", "executor_view_media", EXECUTOR),
    (f"executor_finish_completion_{REQUEST_NUMBER}", f"{H}.requests.executor", "executor_finish_completion", EXECUTOR),
]


@pytest.mark.parametrize("data,module,name,ctx", LIVE_NEIGHBOURS,
                         ids=[c[0] for c in LIVE_NEIGHBOURS])
def test_live_neighbours_untouched(data, module, name, ctx):
    assert _cb(data, **ctx) == (module, name)


def test_start_command_unchanged():
    """BUG-158 `start_onboarding` был перекрыт `base.cmd_start` (start_router
    включается первым) — ретайр перекрытого хендлера /start не меняет."""
    assert _msg("/start", **APPLICANT) == (f"{H}.base", "cmd_start")
