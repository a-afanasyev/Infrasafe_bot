"""ARCH-116: AST-гейт — показ времени смен только через канон бизнес-зоны.

Дефект был не в одной формуле, а в том, что «как показать время» решалось по
месту: 70 вызовов `strftime` на UTC-инстантах и дневные бакеты по UTC-дате
(`date.today()`, `func.date(col)`). Пока способ показа не единственный, любая
новая строка тихо вернёт UTC-часы, и найдётся это только глазами пользователя.

Гейт ловит в SWEPT_FILES три паттерна:
  (a) `<expr>.strftime(...)` — форматирование мимо `utils/business_time`;
  (b) `date.today()` / `datetime.today()` — календарный «сегодня» по зоне сервера
      вместо `business_today()`;
  (c) `func.date(<колонка>)` — бакет дня по зоне сессии БД вместо окна
      `business_day(s)_window(...)`.

Почему AST, а не поведенческий тест: поведение уже закреплено юнит-тестами
(`tests/utils/test_business_time.py`) и хендлерными (`test_my_shifts_business_tz.py`).
Гейт стоит от РЕГРЕССИИ в новых строках, а такую регрессию поведенческий тест не
видит, пока для неё не написан отдельный сценарий.

ВНЕ SWEPT осознанно:
  * `keyboards/shift_management.py` — единственный `strftime` там по календарной
    `date` (`'%d.%m (%A)'`, построена от `business_today()`), конвертировать
    нечего. Попутная находка не из этого пункта: `%A` даёт английское имя дня
    (`Thursday`) и RU/UZ-пользователю тоже — это локализация, не таймзона.
  * `services/shift_planning_service.py`, `services/shift_assignment_service.py`,
    `services/recommendation_engine.py` — там ещё ~24 бакета `func.date(...)`, но
    это планировочные/скоринговые движки: смена бакета меняет РЕШЕНИЯ алгоритма,
    а не только показ. Отдельная задача со своими тестами (см. описание PR).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parents[2] / "uk_management_bot"

SWEPT_FILES: tuple[str, ...] = (
    "handlers/my_shifts.py",
    "handlers/shifts.py",
    "handlers/shift_transfer.py",
    "handlers/shift_management/schedule.py",
    "handlers/shift_management/analytics.py",
    "handlers/shift_management/assignment_a.py",
    "handlers/shift_management/assignment_b.py",
    "handlers/shift_management/auto_planning.py",
    "handlers/shift_management/manual_planning.py",
    "handlers/shift_management/shared.py",
    "keyboards/my_shifts.py",
    "keyboards/shift_transfer.py",
    "services/notification_service.py",
    "services/shift_transfer_service.py",
    "services/shift_management_service.py",
    # ARCH-135 фаза 1: дневные бакеты статистики дашборда переведены на
    # бизнес-дату (Python-бакет через business_date_of; func.date снят).
    "api/requests/stats_service.py",
    "api/requests/stats_router.py",
)


def _is_strftime(node: ast.Call) -> bool:
    return isinstance(node.func, ast.Attribute) and node.func.attr == "strftime"


def _is_today_call(node: ast.Call) -> bool:
    """`date.today()` / `datetime.today()` в любом алиасинге модуля.

    Проверяется имя атрибута, а не полный путь: `today()` у чего-либо иного в
    этих файлах не встречается, а привязка к `datetime`-именам позволила бы
    обойти гейт алиасом.
    """
    return isinstance(node.func, ast.Attribute) and node.func.attr == "today"


def _is_func_date(node: ast.Call) -> bool:
    """`func.date(...)` — SQL-бакет по зоне сессии БД."""
    return (
        isinstance(node.func, ast.Attribute)
        and node.func.attr == "date"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "func"
    )


_FMT_HELPERS = {
    "fmt_time", "fmt_time_seconds", "fmt_date", "fmt_datetime",
    "fmt_day_month", "fmt_day_month_time",
}


def _is_truncated_arg_to_fmt(node: ast.Call) -> bool:
    """`fmt_*(<инстант>.date())` — зона выброшена ДО конвертации.

    `.date()` срезает aware-UTC инстант до КАЛЕНДАРНОЙ даты по UTC, а
    `_wall_value` календарную дату отдаёт как есть (конвертировать её нечем).
    Итог самый неприятный из возможных: на одном экране дата вчерашняя, а время
    рядом — уже ташкентское. Ровно так и уехал `assignment_b.py` при переводе на
    хелперы: механическая замена `X.date().strftime(...)` → `fmt_date(X.date())`
    выглядит корректной и молча теряет конвертацию.
    """
    if not (isinstance(node.func, ast.Name) and node.func.id in _FMT_HELPERS):
        return False
    return any(
        isinstance(arg, ast.Call)
        and isinstance(arg.func, ast.Attribute)
        and arg.func.attr == "date"
        and not (isinstance(arg.func.value, ast.Name) and arg.func.value.id == "func")
        for arg in node.args
    )


def _is_datetime_combine(node: ast.Call) -> bool:
    """`datetime.combine(...)` — рукописная граница дня.

    Даже с `tzinfo=timezone.utc` (то есть мимо гейта `test_shift_tz_inventory`)
    это окно UTC-суток: сначала берут `.date()` инстанта, потом строят из неё
    полночь. Окно бизнес-дня собирает `business_day_window()`.
    """
    return isinstance(node.func, ast.Attribute) and node.func.attr == "combine"


def collect_violations(source: str, label: str) -> list[str]:
    tree = ast.parse(source)
    violations: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if _is_truncated_arg_to_fmt(node):
            violations.append(
                f"{label}:{node.lineno}: fmt_*(x.date()) — .date() срезает инстант по UTC "
                f"ДО конвертации; передавай сам инстант"
            )
        elif _is_datetime_combine(node):
            violations.append(
                f"{label}:{node.lineno}: datetime.combine(...) — окно UTC-суток; "
                f"используй business_day_window()"
            )
        elif _is_strftime(node):
            violations.append(
                f"{label}:{node.lineno}: .strftime(...) — показ только через "
                f"utils/business_time (fmt_time/fmt_date/fmt_datetime/...)"
            )
        elif _is_today_call(node):
            violations.append(
                f"{label}:{node.lineno}: date.today() — «сегодня» по зоне сервера; "
                f"используй business_today()"
            )
        elif _is_func_date(node):
            violations.append(
                f"{label}:{node.lineno}: func.date(колонка) — бакет по зоне сессии БД; "
                f"используй окно business_day_window()/business_days_window()"
            )
    return violations


@pytest.mark.parametrize("rel", SWEPT_FILES)
def test_swept_file_exists(rel: str):
    """Переименование файла не должно молча опустошать гейт."""
    assert (PACKAGE_ROOT / rel).is_file(), f"{rel} не найден — обнови SWEPT_FILES"


def test_shift_display_goes_through_business_time():
    all_violations: list[str] = []
    for rel in SWEPT_FILES:
        path = PACKAGE_ROOT / rel
        all_violations.extend(collect_violations(path.read_text(encoding="utf-8"), rel))
    assert not all_violations, "\n" + "\n".join(all_violations)


# ── Самопроверка гейта: нарушитель — валидная программа, и он ловится ────────

VIOLATORS = {
    "strftime": "def f(shift):\n    return shift.start_time.strftime('%H:%M')\n",
    "today": "from datetime import date\n\ndef f():\n    return date.today()\n",
    "func_date": (
        "from sqlalchemy import func\n\n"
        "def f(col, day):\n    return func.date(col) == day\n"
    ),
    "truncated_arg": (
        "from uk_management_bot.utils.business_time import fmt_date\n\n"
        "def f(shift):\n    return fmt_date(shift.start_time.date())\n"
    ),
    "datetime_combine": (
        "from datetime import datetime, time, timezone\n\n"
        "def f(day):\n    return datetime.combine(day, time.min, tzinfo=timezone.utc)\n"
    ),
}


@pytest.mark.parametrize("name,source", sorted(VIOLATORS.items()))
def test_gate_catches_synthetic_violator(name: str, source: str):
    ast.parse(source)  # нарушитель обязан быть валидной программой
    assert collect_violations(source, f"<{name}>"), f"гейт не поймал {name}"


def test_gate_is_quiet_on_canonical_code():
    """Контроль: канонический показ гейт не трогает — иначе он ловит «всё»."""
    canonical = (
        "from uk_management_bot.utils.business_time import business_today, fmt_time\n\n"
        "def f(shift):\n"
        "    today = business_today()\n"
        "    return today, fmt_time(shift.start_time)\n"
    )
    assert collect_violations(canonical, "<canonical>") == []
