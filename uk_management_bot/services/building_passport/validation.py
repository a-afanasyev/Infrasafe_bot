"""Проверки значений паспорта дома.

Два уровня:

* `normalize` — приём одного значения. Тип и диапазон проверяются сразу:
  отрицательная длина или текст в числовом поле не сохраняются никогда;
* `issues` / `missing` — сверки сумм и полнота. Черновик с ними сохраняется,
  но статус «Заполнен» с ними недоступен.

Значения — плоский словарь: ключ поля → скаляр, ключ группы → список строк,
`<ключ>_text` → расшифровка варианта «другое».
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from typing import Any, Mapping, Optional

from . import schema
from .schema import Field, Group

TEXT_MAX = 500
MAX_ROWS = 30
NUMBER_MAX = 1_000_000_000
YEAR_MIN = 1900
TEXT_SUFFIX = "_text"
_EPS = 0.01


class BadValue(ValueError):
    """Значение не принимается: код причины и ключ поля."""

    def __init__(self, key: str, code: str):
        super().__init__(f"{key}: {code}")
        self.key, self.code = key, code


@dataclass(frozen=True)
class Issue:
    key: str
    code: str


@lru_cache(maxsize=1)
def _fields() -> dict[str, Field]:
    return {f.key: f for f in schema.iter_fields()}


@lru_cache(maxsize=1)
def _groups() -> dict[str, Group]:
    return {g.key: g for g in schema.iter_groups()}


def _has_other(item: Field) -> bool:
    return any(o.other for o in item.options)


# ── приём значения ──────────────────────────────────────────────────────────

def _number(key: str, raw: Any, item: Field) -> Optional[float | int]:
    if isinstance(raw, bool):
        raise BadValue(key, "not_a_number")
    if isinstance(raw, str):
        text = raw.replace(" ", "").replace(" ", "").replace(",", ".")
        if not text:
            return None
        try:
            raw = float(text)
        except ValueError:
            raise BadValue(key, "not_a_number") from None
    if not isinstance(raw, (int, float)) or raw != raw:  # NaN
        raise BadValue(key, "not_a_number")
    if raw < 0:
        raise BadValue(key, "negative")
    if raw > NUMBER_MAX:
        raise BadValue(key, "too_large")
    if item.type == "int":
        if raw != int(raw):
            raise BadValue(key, "not_an_integer")
        raw = int(raw)
    else:
        raw = round(float(raw), 3)
    if item.unit == "%" and raw > 100:
        raise BadValue(key, "percent_range")
    if item.unit == "год" and not YEAR_MIN <= raw <= date.today().year:
        raise BadValue(key, "year_range")
    return raw


def _text(key: str, raw: Any) -> Optional[str]:
    if not isinstance(raw, str):
        raise BadValue(key, "not_a_text")
    text = raw.strip()
    if len(text) > TEXT_MAX:
        raise BadValue(key, "too_long")
    return text or None


def _scalar(key: str, raw: Any, item: Field) -> Any:
    if raw is None:
        return None
    if item.type in ("int", "decimal"):
        return _number(key, raw, item)
    if item.type == "text":
        return _text(key, raw)
    if raw == "":
        return None
    if not isinstance(raw, str) or raw not in {o.key for o in item.options}:
        raise BadValue(key, "unknown_option")
    return raw


def _rows(key: str, raw: Any, group: Group) -> list[dict]:
    if raw is None:
        return []
    if not isinstance(raw, list) or not all(isinstance(r, dict) for r in raw):
        raise BadValue(key, "not_rows")
    if len(raw) > MAX_ROWS:
        raise BadValue(key, "too_many_rows")
    by_key = {f.key: f for f in group.fields}
    out: list[dict] = []
    for row in raw:
        clean: dict = {}
        for name, value in row.items():
            item = by_key.get(name)
            if item is None:
                raise BadValue(key, "unknown_field")
            if item.computed:
                continue  # площадь строки клиент присылает обратно — считаем сами
            value = _scalar(key, value, item)
            if value is not None:
                clean[name] = value
        if clean:
            out.append(clean)
    return out


def normalize(key: str, raw: Any) -> Any:
    """Привести значение к типу поля либо отказать (`BadValue`)."""
    if key in _groups():
        return _rows(key, raw, _groups()[key])
    if key.endswith(TEXT_SUFFIX):
        owner = _fields().get(key[: -len(TEXT_SUFFIX)])
        if owner is None or not _has_other(owner):
            raise BadValue(key, "unknown_field")
        return None if raw is None else _text(key, raw)
    item = _fields().get(key)
    if item is None:
        raise BadValue(key, "unknown_field")
    if item.computed:
        raise BadValue(key, "computed")
    return _scalar(key, raw, item)


# ── вычисляемые пункты ──────────────────────────────────────────────────────

def _opening_rows(rows: list[dict]) -> list[dict]:
    out = []
    for row in rows:
        size = [row.get(k) for k in ("count", "width", "height")]
        rest = {k: val for k, val in row.items() if k != "area"}
        if all(x is not None for x in size):
            rest["area"] = round(size[0] * size[1] * size[2], 3)
        out.append(rest)
    return out


def _total(values: Mapping[str, Any], keys: tuple[str, ...]) -> Optional[int]:
    parts = [values.get(k) for k in keys]
    return None if all(p is None for p in parts) else sum(p or 0 for p in parts)


def with_computed(values: Mapping[str, Any]) -> dict:
    """Копия значений с вычисляемыми пунктами (исходный словарь не меняется)."""
    out = {k: val for k, val in values.items() if k not in _fields() or not _fields()[k].computed}
    for group in ("windows", "doors"):
        if out.get(group):
            out[group] = _opening_rows(out[group])
    windows = out.get("windows") or []
    if windows:
        # Итог 2.19 — по всем окнам дома, включая типы вне формы (решение владельца).
        out["windows_total_count"] = sum(r.get("count") or 0 for r in windows)
        out["windows_total_area"] = round(sum(r.get("area") or 0 for r in windows), 3)
    for total, parts in (("planted_total", ("planted_conifer", "planted_leaf", "planted_shrub")),
                         ("existing_total", ("existing_conifer", "existing_leaf", "existing_shrub"))):
        value = _total(out, parts)
        if value is not None:
            out[total] = value
    return out


# ── условия показа ──────────────────────────────────────────────────────────

def applicable(values: Mapping[str, Any]) -> set[str]:
    """Ключи полей и групп, которые сейчас применимы (с учётом `show_if`)."""
    items = [*_fields().values(), *_groups().values()]
    out = {item.key for item in items if item.show_if is None}
    changed = True
    while changed:  # цепочки: состояние слоёв зависит от слоёв, те — от чердака
        changed = False
        for item in items:
            if item.key in out or item.show_if is None:
                continue
            parent, allowed = item.show_if
            if parent in out and values.get(parent) in allowed:
                out.add(item.key)
                changed = True
    return out


# ── сверки ──────────────────────────────────────────────────────────────────

_SUM_100 = (("facade_ok_pct", "facade_bad_pct"),
            ("basement_repaired_pct", "basement_partly_pct", "basement_needs_pct"))
_SUM_TOTAL = (("vru_total", ("vru_ok", "vru_bad")), ("grsh_total", ("grsh_ok", "grsh_bad")))
_PIPE_GROUPS = ("heating_pipes", "cold_pipes", "hot_pipes", "sewer_pipes")


def issues(values: Mapping[str, Any]) -> list[Issue]:
    """Противоречия в уже принятых значениях. Пустой список — сверки сошлись."""
    out: list[Issue] = []
    shown = applicable(values)
    for keys in _SUM_100:
        parts = [values.get(k) for k in keys]
        if all(p is not None for p in parts) and abs(sum(parts) - 100) > _EPS:
            out.append(Issue(keys[-1], "sum_100"))
    for total, parts in _SUM_TOTAL:
        nums = [values.get(total), *(values.get(k) for k in parts)]
        if all(n is not None for n in nums) and nums[0] != sum(nums[1:]):
            out.append(Issue(total, "sum_total"))
    for group in _PIPE_GROUPS:
        if group not in shown:
            continue
        for row in values.get(group) or []:
            nums = [row.get(k) for k in ("length", "ok_length", "bad_length")]
            if all(n is not None for n in nums) and abs(nums[0] - nums[1] - nums[2]) > _EPS:
                out.append(Issue(group, "pipe_condition_sum"))
                break
    for key, item in _fields().items():
        if key not in shown or not item.options:
            continue
        chosen = next((o for o in item.options if o.key == values.get(key)), None)
        if chosen is not None and chosen.other and chosen.key == "other" and not values.get(key + TEXT_SUFFIX):
            out.append(Issue(key, "other_text_required"))
    return out


# ── полнота ─────────────────────────────────────────────────────────────────

def _required(values: Mapping[str, Any]) -> list[str]:
    shown = applicable(values)
    fields = [k for k, f in _fields().items() if k in shown and not f.computed]
    return [*fields, *(k for k in _groups() if k in shown)]


def missing(values: Mapping[str, Any], *, unknown: Mapping[str, str], absent: set[str]) -> list[str]:
    """Применимые пункты без ответа. «Нет данных» и «нет в доме» — ответы."""
    out = []
    for key in _required(values):
        if key in _groups():
            if not values.get(key) and key not in absent and key not in unknown:
                out.append(key)
        elif values.get(key) is None and key not in unknown:
            out.append(key)
    return out


def progress(values: Mapping[str, Any], *, unknown: Mapping[str, str], absent: set[str]) -> tuple[int, int]:
    total = len(_required(values))
    return total - len(missing(values, unknown=unknown, absent=absent)), total
