"""BUG-166: одна семантика подбора по специализациям во всех точках.

Проект отвечал на вопрос «подходит ли исполнитель под требование по
специализациям» ДЕВЯТЬЮ разными способами:

* `has_required_specs` (перевод смены, бот+веб) — ВСЕ (`issubset`);
* `scoring.py` (авто-подбор на смену) — ВСЕ, блокирующая оценка −1.0;
* `planning.py` (генерация смен из шаблона) — ЛЮБАЯ + `universal` у исполнителя;
* `ShiftTemplate.matches_specialization` — ЛЮБАЯ, без нормализации;
* `Shift.can_handle_specialization` — членство + `universal` у СМЕНЫ;
* `assignment_b.handle_select_shift_for_assignment` — ЛЮБАЯ, сырой json;
* `assignment_b.handle_assign_executor_to_shift` — ВСЕ, сырой json;
* `assignment_b.handle_force_assign` — ВСЕ, сырой json;
* `auto_manager/rule_engine.select_executor` — членство БЕЗ джокера, и тут же
  рядом, в той же функции, `can_handle_specialization` джокер учитывал.

Три из них — в одном файле, и первые два противоречили друг другу: список
кандидатов предлагал исполнителя, а гвард назначения тут же отказывал ему
«отсутствуют специализации».

Решения владельца (2026-08-17):

1. **ЛЮБАЯ** везде. Фокус смены — это «что смена покрывает», а не «чем один
   человек обязан владеть одновременно»: заявка и так попадает на смену, если
   её специализация ЕСТЬ в фокусе (`can_handle_specialization`).
2. `universal` — **симметричный джокер**: в требовании = «подойдёт кто угодно»,
   у исполнителя = «умеет всё».

Матрица ниже — единственный источник истины; каждый консьюмер обязан дать по
ней те же вердикты.
"""
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from uk_management_bot.database.models.shift import Shift
from uk_management_bot.database.models.shift_template import ShiftTemplate
from uk_management_bot.services.shift_assignment_service import ScoringEngine
from uk_management_bot.services.shift_planning_service import ShiftPlanningService
from uk_management_bot.utils.specializations import (
    has_required_specs,
    has_required_template_specs,
    matches_required_specs,
)

# (специализации исполнителя, требование, ожидаемый вердикт, почему)
# Канонические токены — их понимает и голый предикат, и любой консьюмер.
CANON_CASES = [
    ([], [], True, "требования нет — подходит любой"),
    (["electrician"], [], True, "пустое требование не ограничивает"),
    (["electrician"], ["electrician"], True, "точное совпадение"),
    (["electrician", "plumber"], ["electrician"], True, "лишние навыки не мешают"),
    (["electrician"], ["electrician", "plumber"],
     True, "ЛЮБАЯ: электрик ведёт электрические заявки смены"),
    (["electrician"], ["plumber"], False, "пересечения нет"),
    ([], ["plumber"], False, "у исполнителя нет специализаций"),
    (["electrician"], ["universal"], True, "universal в требовании — джокер"),
    ([], ["universal"], True, "джокер в требовании принимает и бесспециализированного"),
    (["universal"], ["plumber"], True, "universal у исполнителя — джокер"),
]

# Legacy-токены: их обязан развернуть парсер по дороге к предикату. Голый
# предикат их не понимает и понимать не должен — см.
# `test_core_predicate_normalizes_nothing`.
ALIAS_CASES = [
    (["electric"], ["electrician"], True, "legacy-алиас нормализуется в канон"),
    (["plumber"], ["maintenance"], False, "maintenance → elevator, не сантехника"),
    (["plumber"], ["plumbing"], True, "legacy-алиас в требовании"),
]

CASES = CANON_CASES + ALIAS_CASES

CANON_IDS = [f"{c[0]}~{c[1]}" for c in CANON_CASES]
IDS = [f"{c[0]}~{c[1]}" for c in CASES]


def _user(specs):
    u = MagicMock()
    u.id = 10
    u.telegram_id = 1010
    u.first_name = "Тест"
    u.last_name = "Исполнителев"
    u.status = "approved"
    u.roles = ["executor"]
    u.specialization = json.dumps(specs) if specs else None
    return u


def _shift_raw(raw):
    """Смена с фокусом ровно в том виде, в каком он лежит в БД."""
    s = MagicMock(spec=Shift)
    s.id = 1
    s.specialization_focus = raw
    s.can_handle_specialization = Shift.can_handle_specialization.__get__(s)
    return s


def _shift(specs):
    return _shift_raw(list(specs))


def _template(specs):
    t = MagicMock(spec=ShiftTemplate)
    t.id = 1
    t.required_specializations = list(specs)
    t.matches_specialization = ShiftTemplate.matches_specialization.__get__(t)
    return t


# ═══ Ядро: общий предикат ═══

@pytest.mark.parametrize("have,need,expected,why", CANON_CASES, ids=CANON_IDS)
def test_core_predicate(have, need, expected, why):
    assert matches_required_specs(set(have), set(need)) is expected, why


def test_core_predicate_normalizes_nothing():
    """Предикат работает с УЖЕ каноническими множествами.

    Нормализация — забота парсеров (`parse_*`): у сторон «умею»/«требуется»
    она асимметрична (`hvac`), и предикат не может выбрать сторону за них.
    """
    assert matches_required_specs({"electric"}, {"electrician"}) is False


# ═══ Точка 1: перевод смены (бот + веб) ═══

@pytest.mark.parametrize("have,need,expected,why", CASES, ids=IDS)
def test_has_required_specs(have, need, expected, why):
    assert has_required_specs(_user(have), _shift(need)) is expected, why


# ═══ Точка 2: генерация смен из шаблона ═══

@pytest.mark.parametrize("have,need,expected,why", CASES, ids=IDS)
def test_has_required_template_specs(have, need, expected, why):
    assert has_required_template_specs(_user(have), _template(need)) is expected, why


@pytest.mark.parametrize("have,need,expected,why", CASES, ids=IDS)
def test_planning_can_executor_work_template(have, need, expected, why):
    service = ShiftPlanningService(MagicMock())
    assert service._can_executor_work_template(_user(have), _template(need)) is expected, why


# ═══ Точка 3: скоринг авто-подбора (блокирующая оценка) ═══

@pytest.mark.parametrize("have,need,expected,why", CASES, ids=IDS)
def test_scoring_blocking_gate(have, need, expected, why):
    """Отрицательная оценка = «не подходит»; она блокирует назначение."""
    engine = ScoringEngine(MagicMock(), {})
    score = engine._calculate_specialization_match(_shift(need), _user(have))
    assert (score >= 0) is expected, why


def test_scoring_ranks_fuller_match_higher():
    """Качество соответствия сохранено: полное покрытие ценнее частичного."""
    engine = ScoringEngine(MagicMock(), {})
    need = ["electrician", "plumber"]
    partial = engine._calculate_specialization_match(_shift(need), _user(["electrician"]))
    full = engine._calculate_specialization_match(_shift(need), _user(need))
    assert 0 <= partial < full


# ═══ Точка 4: шаблон отвечает на «подхожу ли я под этот набор» ═══

@pytest.mark.parametrize("have,need,expected,why", CASES, ids=IDS)
def test_template_matches_specialization(have, need, expected, why):
    assert _template(need).matches_specialization(have) is expected, why


# ═══ Точка 5: «покрывает ли смена специализацию заявки» ═══
# Форма другая (одна специализация против фокуса), но правила `universal` и
# нормализации — те же.

@pytest.mark.parametrize("focus,spec,expected,why", [
    ([], "plumber", True, "смена без фокуса покрывает всё"),
    (["plumber"], "plumber", True, "точное совпадение"),
    (["plumber", "electrician"], "electrician", True, "специализация есть в фокусе"),
    (["plumber"], "electrician", False, "специализации нет в фокусе"),
    (["universal"], "electrician", True, "universal в фокусе — джокер"),
    (["electric"], "electrician", True, "legacy-алиас в фокусе нормализуется"),
    (["elevator"], "maintenance", True, "legacy-алиас в запросе нормализуется"),
    (["carpentry"], "electrician", False,
     "нераспознанный фокус НЕ делает смену универсальной"),
])
def test_shift_can_handle_specialization(focus, spec, expected, why):
    assert _shift(focus).can_handle_specialization(spec) is expected, why


def test_unresolvable_focus_fails_closed():
    """Смена с опечаткой в фокусе не должна принимать ВСЁ.

    Ловушка перевода на канон: проверять «требования нет» надо по СЫРОМУ полю.
    Сравнение распарсенного набора с пустотой превращает нераспознанный токен
    в «ограничений нет» — до BUG-166 сравнение шло по сырому списку, и такая
    строка не подходила никому.
    """
    shift = _shift(["carpentry", "painting"])
    assert all(
        shift.can_handle_specialization(spec) is False
        for spec in ("electrician", "plumber", "cleaning")
    )


# Ту же ловушку надо проверять во ВСЕХ точках, а не только там, где её нашли:
# первый раз fail-closed поставили только смене, и зеркальная точка (шаблон)
# осталась fail-open — гвард инвертировался с «не подходит никто» на
# «подходит любой».

@pytest.mark.parametrize("check", [
    pytest.param(lambda u, t: has_required_template_specs(u, t), id="has_required_template_specs"),
    pytest.param(lambda u, t: ShiftPlanningService(MagicMock())._can_executor_work_template(u, t),
                 id="planning"),
    pytest.param(lambda u, t: t.matches_specialization(["electrician"]), id="matches_specialization"),
])
def test_unresolvable_template_requirement_fails_closed(check):
    assert check(_user(["electrician"]), _template(["carpentry"])) is False


def test_unresolvable_focus_fails_closed_in_transfer_guard():
    """Гвард перевода смены (REG-02, бот + `api/shifts`) — самый чувствительный.

    Он единственный из четырёх точек был fail-open и ДО BUG-166, поэтому его
    легко забыть: откат строки в `has_required_specs` не роняет ни один другой
    тест и проходит AST-ратчет.
    """
    assert has_required_specs(_user(["electrician"]), _shift(["carpentry"])) is False


@pytest.mark.parametrize("raw", [None, [], "", "   ", "[]", ",", ["", " "]])
def test_blank_requirement_is_absence_not_garbage(raw):
    """Пусто во всех видах — это «требования нет», а не «не резолвится».

    Граница fail-closed проходит по НАЛИЧИЮ токенов: `"[]"` и `","` токенов не
    дают, поэтому ограничений нет; `"carpentry"` токен даёт, но канон его не
    знает — вот там и отказ.
    """
    assert has_required_specs(_user([]), _shift_raw(raw)) is True


def test_unresolvable_focus_blocks_scoring():
    """У скоринга «не подходит» выражается отрицательной оценкой."""
    engine = ScoringEngine(MagicMock(), {})
    score = engine._calculate_specialization_match(_shift(["carpentry"]), _user(["electrician"]))
    assert score < 0


def test_predicate_returns_real_bool():
    """Вердикт — настоящий bool: вызывающие сравнивают его через `is`."""
    assert type(matches_required_specs({"electrician"}, {"electrician"})) is bool
    assert type(matches_required_specs({"electrician"}, {"plumber"})) is bool


# ═══ Точки 6 и 7: список кандидатов и гвард назначения (assignment_b) ═══
# Оба — живой UI менеджера, и до BUG-166 они отвечали по-разному.

def _callback(data):
    cb = MagicMock()
    cb.data = data
    cb.from_user.id = 1
    cb.answer = AsyncMock()
    cb.message.edit_text = AsyncMock()
    return cb


def _assignment_env(monkeypatch, shift, executor):
    from uk_management_bot.handlers.shift_management import assignment_b as mod

    service = MagicMock()
    service.get_shift.return_value = shift
    service.get_user.return_value = executor
    service.list_approved_users.return_value = [executor]
    service.count_shifts_for_user_on_day.return_value = 0
    service.list_overlapping_shifts.return_value = []
    service.assign_executor.return_value = True
    monkeypatch.setattr(mod, "ShiftManagementService", lambda db: service)
    monkeypatch.setattr(mod, "get_user_language", lambda *a, **kw: "ru")
    return mod, service


def _shift_for_handler(specs):
    """Смена в хендлере ходит через реальные атрибуты (время, зона)."""
    from datetime import datetime, timezone
    s = _shift(specs)
    s.start_time = datetime(2026, 8, 17, 9, 0, tzinfo=timezone.utc)
    s.end_time = datetime(2026, 8, 17, 18, 0, tzinfo=timezone.utc)
    s.geographic_zone = None
    s.user_id = None
    return s


@pytest.mark.asyncio
async def test_candidate_list_offers_partial_match(monkeypatch):
    """Электрик виден в списке кандидатов на смену «электрика + сантехника»."""
    shift = _shift_for_handler(["electrician", "plumber"])
    executor = _user(["electrician"])
    mod, _ = _assignment_env(monkeypatch, shift, executor)

    callback = _callback("select_shift_for_assignment:1")
    await mod.handle_select_shift_for_assignment(
        callback, MagicMock(set_state=AsyncMock()),
        db=MagicMock(), user=MagicMock(), roles=["manager"])

    callback.message.edit_text.assert_awaited_once()
    markup = callback.message.edit_text.await_args.kwargs["reply_markup"]
    buttons = [b.callback_data for row in markup.inline_keyboard for b in row]
    assert any(b.startswith("assign_executor_to_shift:") for b in buttons), \
        "исполнитель с частичным совпадением обязан попасть в список"


@pytest.mark.asyncio
async def test_assignment_guard_accepts_partial_match(monkeypatch):
    """…и назначение того же исполнителя не отказывает ему постфактум.

    Ровно это противоречие было видно менеджеру: кандидат в списке есть, а при
    выборе — «отсутствуют специализации».
    """
    shift = _shift_for_handler(["electrician", "plumber"])
    executor = _user(["electrician"])
    mod, service = _assignment_env(monkeypatch, shift, executor)

    callback = _callback("assign_executor_to_shift:1:10")
    await mod.handle_assign_executor_to_shift(
        callback, MagicMock(clear=AsyncMock()),
        db=MagicMock(), user=MagicMock(), roles=["manager"])

    service.assign_executor.assert_called_once()


def _assert_refused(callback, service_call):
    """Отказ = назначения не было И менеджер увидел объяснение.

    Одного `assert_not_called` мало: оба хендлера обёрнуты глухим
    `except Exception`, поэтому ЛЮБОЕ падение в ветке отказа выглядит как
    корректный отказ. Ровно так BUG-161 (`ImportError` → `UnboundLocalError`)
    доехал до прода в этом же файле и именно в этих ветках.
    """
    service_call.assert_not_called()
    callback.message.edit_text.assert_awaited_once()
    callback.answer.assert_awaited()


@pytest.mark.asyncio
async def test_assignment_guard_still_refuses_disjoint(monkeypatch):
    """Совсем несовпадающая специализация по-прежнему отклоняется."""
    shift = _shift_for_handler(["plumber"])
    executor = _user(["electrician"])
    mod, service = _assignment_env(monkeypatch, shift, executor)

    callback = _callback("assign_executor_to_shift:1:10")
    await mod.handle_assign_executor_to_shift(
        callback, MagicMock(clear=AsyncMock()),
        db=MagicMock(), user=MagicMock(), roles=["manager"])

    _assert_refused(callback, service.assign_executor)


# Третий сайт того же вопроса в этом файле — «назначить принудительно».
# «Принудительно» относится к конфликту РАСПИСАНИЯ, квалификацию оно не
# отменяет, поэтому предикат обязан быть тем же.

@pytest.mark.asyncio
async def test_force_assign_accepts_partial_match(monkeypatch):
    shift = _shift_for_handler(["electrician", "plumber"])
    executor = _user(["electrician"])
    mod, service = _assignment_env(monkeypatch, shift, executor)

    callback = _callback("force_assign:1:10")
    await mod.handle_force_assign(
        callback, MagicMock(clear=AsyncMock()),
        db=MagicMock(), user=MagicMock(), roles=["manager"])

    service.force_assign_executor.assert_called_once()


@pytest.mark.asyncio
async def test_force_assign_still_refuses_disjoint(monkeypatch):
    shift = _shift_for_handler(["plumber"])
    executor = _user(["electrician"])
    mod, service = _assignment_env(monkeypatch, shift, executor)

    callback = _callback("force_assign:1:10")
    await mod.handle_force_assign(
        callback, MagicMock(clear=AsyncMock()),
        db=MagicMock(), user=MagicMock(), roles=["manager"])

    _assert_refused(callback, service.force_assign_executor)


# ═══ Ратчет: восьмой копии правил быть не должно ═══

# Все места, отвечающие на вопрос «подходит ли исполнитель под требование».
# Список закрытый намеренно: широкий regex по репозиторию ловил сравнение РОЛЕЙ
# и конфликт «смена ↔ смена» — это другие вопросы, и глушить их `noqa` значило
# бы приучить гейт к исключениям.
SPEC_CONSUMERS = [
    "api/shifts/service/web_transfers.py",
    "database/models/shift.py",
    "database/models/shift_template.py",
    "handlers/admin/assignment.py",
    "handlers/admin/shared.py",
    "handlers/requests/executor.py",
    "handlers/shift_management/assignment_b.py",
    "services/auto_manager/rule_engine.py",
    "services/shift_assignment_service/scoring.py",
    "services/shift_planning_service/planning.py",
    "services/shift_transfer_service.py",
]

CANON_PREDICATES = frozenset({
    "matches_required_specs",
    "matches_raw_requirement",
    "has_required_specs",
    "has_required_template_specs",
})


@pytest.mark.parametrize("relpath", SPEC_CONSUMERS)
def test_consumer_uses_canonical_predicate(relpath):
    """Каждый консьюмер ВЫЗЫВАЕТ канон, а не считает вердикт сам.

    Расхождение накопилось именно так: каждое место писало своё
    `issubset`/`intersection`/`in`, и копии разъехались незаметно для тестов.

    Проверка по AST, а не поиском подстроки: в `assignment_b.py` имя
    `has_required_specs` встречается ещё и в комментарии (BUG-161), и
    подстрочный гейт остался бы зелёным даже после удаления всех вызовов.
    """
    import ast
    import pathlib

    tree = ast.parse(
        (pathlib.Path(__file__).resolve().parents[1] / relpath).read_text(encoding="utf-8"))
    called = {
        node.func.id if isinstance(node.func, ast.Name) else node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, (ast.Name, ast.Attribute))
    }
    assert called & CANON_PREDICATES, (
        f"{relpath}: вердикт по специализациям обязан идти через "
        f"`matches_required_specs` и его обёртки (BUG-166)"
    )


@pytest.mark.parametrize("relpath", SPEC_CONSUMERS)
def test_consumer_has_no_private_set_verdict(relpath):
    """…и не оставляет рядом собственное множественное сравнение навыков."""
    import pathlib
    import re

    source = (pathlib.Path(__file__).resolve().parents[1] / relpath).read_text(encoding="utf-8")
    # Ловим формы, которые бывают ТОЛЬКО вердиктом. `intersection`/`issubset`
    # сюда намеренно не входят: в `scoring.py` они считают КАЧЕСТВО
    # соответствия уже после вердикта, и запрет вынудил бы глушить гейт.
    private = re.compile(
        r"(any\(\s*\w+\s+in\s+\w*executor_specs)"            # своя проверка «ЛЮБАЯ»
        r"|(missing_specs\s*=\s*set\()"                      # своя проверка «чего не хватает»
    )
    offenders = [
        f"{relpath}:{n}: {line.strip()}"
        for n, line in enumerate(source.splitlines(), 1)
        if private.search(line)
    ]
    assert offenders == [], (
        "сравнение специализаций мимо `matches_required_specs` (BUG-166):\n"
        + "\n".join(offenders)
    )
