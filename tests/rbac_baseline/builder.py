#!/usr/bin/env python3
"""RBAC этап 0: характеризационный снимок текущих прав («матрица как есть»).

Зачем. Переход на действия вместо имён ролей (RBAC A1, вариант O3) обязан НЕ
менять, кто что может. Снимок фиксирует РЕЗУЛЬТАТ проверок, а не их механизм:
каждый гейт вызывается по-настоящему с синтетическими пользователями всех
ролевых профилей прода, и в файл пишется «точка входа × профиль → пропуск».
Замена `require_roles("manager")` на проверку действия обязана дать ту же
матрицу — иначе это изменение прав, и оно оформляется отдельно.

Что снимается:
  * API ядра и API охраны — каждый маршрут: публичный / любой вошедший /
    гейт по ролям с множеством пропускаемых профилей;
  * бот — декораторы (`require_role`/`require_action`), root-фильтры роутеров
    (`RoleGate`/`ActionGate`) и фильтры режима меню `RoleFilter` (по
    `active_role`) — с вычисленным результатом, ключи нейтральны к механизму;
  * инвентарь сравнений роли со строкой-именем в телах функций
    (`inline_checks.json`, двунаправленный ратчет).

Чего НЕ снимает: ветвления внутри тел функций (их предикаты пиннит
tests/services/test_rbac_role_predicates.py), объектные проверки
(check_request_access, workflow guards) — у них свои тесты.

Команды:
    python tests/rbac_baseline/builder.py --check   # сверить с tests/rbac_baseline/*.json
    python tests/rbac_baseline/builder.py --write   # перегенерировать (только осознанно!)
"""
from __future__ import annotations

import argparse
import ast
import asyncio
import importlib
import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Iterable

ROOT = Path(__file__).resolve().parents[2]
BASELINE_DIR = Path(__file__).resolve().parent
HANDLERS_DIR = ROOT / "uk_management_bot" / "handlers"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@dataclass(frozen=True)
class Profile:
    """Синтетический пользователь. Набор — все сочетания ролей, найденные на
    обоих продах 2026-09-28, плюс граничные случаи (пустые роли, pending)."""

    name: str
    roles: tuple[str, ...]
    status: str = "approved"


PROFILES: tuple[Profile, ...] = (
    Profile("applicant", ("applicant",)),
    Profile("executor", ("executor",)),
    Profile("inspector", ("inspector",)),
    Profile("manager", ("manager",)),
    Profile("admin", ("admin",)),
    Profile("system_admin", ("system_admin",)),
    Profile("security_operator", ("security_operator",)),
    Profile("resource_meter_entry", ("resource_meter_entry",)),
    Profile("executor+inspector", ("executor", "inspector")),
    Profile("executor+resource_meter_entry", ("executor", "resource_meter_entry")),
    Profile("applicant+manager", ("applicant", "manager")),
    Profile("executor+inspector+manager", ("executor", "inspector", "manager")),
    Profile("applicant+executor+manager", ("applicant", "executor", "manager")),
    Profile("applicant+executor+manager+system_admin",
            ("applicant", "executor", "manager", "system_admin")),
    Profile("superuser7", ("admin", "applicant", "executor", "inspector", "manager",
                           "resource_meter_entry", "system_admin")),
    Profile("empty_roles", ()),
    Profile("applicant@pending", ("applicant",), "pending"),
    Profile("executor@pending", ("executor",), "pending"),
    Profile("manager@pending", ("manager",), "pending"),
)


def run_coro(coro):
    """Выполнить корутину на СОБСТВЕННОМ loop, не трогая текущий.

    `asyncio.run` в конце сбрасывает текущий loop (`set_event_loop(None)`), и
    соседние тесты на `get_event_loop()` в Python 3.13 падают по порядку
    запуска. Снимок вызывается из тестов — он обязан не загрязнять окружение.
    """
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def fake_user(profile: Profile) -> SimpleNamespace:
    return SimpleNamespace(
        id=1000, telegram_id=1000, roles=json.dumps(list(profile.roles)),
        status=profile.status, deleted_at=None,
        active_role=profile.roles[0] if profile.roles else None,
        language="ru", first_name="T", last_name="U", username=None,
    )


def resolved_roles(profile: Profile) -> list[str]:
    from uk_management_bot.utils.auth_helpers import get_user_roles
    return get_user_roles(fake_user(profile))


def _allowed(predicate: Callable[[Profile], bool]) -> list[str]:
    return [p.name for p in PROFILES if predicate(p)]


# --------------------------------------------------------------------------- API

def _user_gates(dependant) -> tuple[bool, list[Callable], list[str]]:
    """→ (зависит ли от get_current_user, гейты-над-пользователем, прочие deps).

    Гейт-над-пользователем — dependency, у которой среди прямых детей есть
    get_current_user (require_roles/require_approved_roles и их будущие замены).
    """
    from uk_management_bot.api.dependencies import get_current_user

    uses_user = False
    gates: list[Callable] = []
    other: set[str] = set()

    def walk(node) -> None:
        nonlocal uses_user
        for dep in node.dependencies:
            call = dep.call
            if call is get_current_user:
                uses_user = True
                continue
            children = [d.call for d in dep.dependencies]
            if get_current_user in children:
                uses_user = True
                gates.append(call)
            else:
                name = getattr(call, "__name__", type(call).__name__)
                if name not in {"get_db", "HTTPBearer"}:
                    other.add(name)
            walk(dep)

    walk(dependant)
    return uses_user, gates, sorted(other)


def _gate_passes(gate: Callable, user: SimpleNamespace) -> bool:
    from fastapi import HTTPException
    try:
        result = gate(user=user)
        if asyncio.iscoroutine(result):
            run_coro(result)
        return True
    except HTTPException as exc:
        if exc.status_code in (401, 403):
            return False
        raise


def snapshot_app(app) -> dict[str, Any]:
    from fastapi.routing import APIRoute, APIWebSocketRoute

    out: dict[str, Any] = {}
    for route in app.routes:
        if isinstance(route, APIRoute):
            keys = [f"{m} {route.path}" for m in sorted(route.methods)]
        elif isinstance(route, APIWebSocketRoute):
            keys = [f"WS {route.path}"]
        else:
            continue
        uses_user, gates, other = _user_gates(route.dependant)
        if not uses_user:
            entry: dict[str, Any] = {"auth": "public"}
        elif not gates:
            entry = {"auth": "user"}
        else:
            entry = {"auth": "roles", "allow": _allowed(
                lambda p: all(_gate_passes(g, fake_user(p)) for g in gates))}
        if other:
            entry["deps"] = other
        for key in keys:
            if key in out and out[key] != entry:
                raise RuntimeError(f"Два разных маршрута под одним ключом: {key}")
            out[key] = entry
    return dict(sorted(out.items()))


def snapshot_core_api() -> dict[str, Any]:
    from uk_management_bot.api.main import app
    return snapshot_app(app)


def snapshot_access_api() -> dict[str, Any]:
    from access_control.app.main import create_app
    return snapshot_app(create_app())


# --------------------------------------------------------------------------- бот

def _module_name(path: Path) -> str:
    return ".".join(path.relative_to(ROOT).with_suffix("").parts)


def _call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Call):
        node = node.func
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _resolve(expr: ast.AST, module) -> Any:
    """Литерал или имя модуля → значение (для аргументов гейтов)."""
    try:
        return ast.literal_eval(expr)
    except ValueError:
        pass
    if isinstance(expr, ast.Name):
        return getattr(module, expr.id)
    if isinstance(expr, ast.Starred):
        return _resolve(expr.value, module)
    raise ValueError(f"не умею вычислить аргумент гейта: {ast.unparse(expr)}")


#: Декораторы-гейты хендлеров бота: прежний (по ролям) и новый (по действию).
#: Снимок хранит РЕЗУЛЬТАТ под нейтральным ключом, поэтому замена одного на
#: другой без изменения прав снимок не трогает.
BOT_DECORATOR_GATES = frozenset({"require_role", "require_action"})
#: Root-фильтры роутеров (`<router>.<observer>.filter(...)`).
BOT_ROOT_GATES = frozenset({"RoleGate", "ActionGate"})


def _decorator_allows(decorator_factory: Callable, args: tuple, kwargs: dict) -> list[str]:
    """Применить настоящий декоратор к зонду и проверить его на всех профилях."""
    sentinel = object()

    async def probe(*_a, **_k):
        return sentinel

    gated = decorator_factory(*args, **kwargs)(probe)

    def ok(p: Profile) -> bool:
        result = run_coro(gated(None, roles=resolved_roles(p), user=fake_user(p)))
        return result is sentinel

    return _allowed(ok)


def _require_role_allows(roles: Iterable[str]) -> list[str]:
    from uk_management_bot.middlewares.auth import require_role

    return _decorator_allows(require_role, (list(roles),), {})


def _root_gate_allows(gate_factory: Callable, args: tuple) -> list[str]:
    gate = gate_factory(*args)
    return _allowed(lambda p: run_coro(
        gate(None, roles=resolved_roles(p), user=fake_user(p))))


def _role_filter_modes(args: tuple, kwargs: dict) -> list[str]:
    """RoleFilter смотрит на active_role (режим меню), а не на набор ролей."""
    from uk_management_bot.filters.role_filter import RoleFilter

    flt = RoleFilter(*args, **kwargs)
    modes = sorted({r for p in PROFILES for r in resolved_roles(p)} | {"applicant"})
    allowed = [m for m in modes if run_coro(flt(None, active_role=m))]
    return allowed + (["<none>"] if run_coro(flt(None, active_role=None)) else [])


def snapshot_bot() -> dict[str, Any]:
    out: dict[str, Any] = {}
    for path in sorted(HANDLERS_DIR.rglob("*.py")):
        rel = path.relative_to(ROOT).as_posix()
        if path.name.startswith("test_") or "/tests/" in rel:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        module = None

        def mod():
            nonlocal module
            if module is None:
                module = importlib.import_module(_module_name(path))
            return module

        # root-фильтры роутера: <router>.<observer>.filter(RoleGate(...)|ActionGate(...))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and _call_name(node) == "filter"
                    and node.args and _call_name(node.args[0]) in BOT_ROOT_GATES):
                gate_call = node.args[0]
                args = tuple(_resolve(a, mod()) for a in gate_call.args)
                args = tuple(tuple(a) if isinstance(a, list) else a for a in args)
                factory = getattr(mod(), _call_name(gate_call))
                target = ast.unparse(node.func.value)
                out[f"{rel}::<{target}.filter>"] = {
                    "root_filter": _root_gate_allows(factory, args)}

        seen: dict[str, int] = {}
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            entry: dict[str, Any] = {}
            for deco in node.decorator_list:
                if isinstance(deco, ast.Call) and _call_name(deco) in BOT_DECORATOR_GATES:
                    factory = getattr(mod(), _call_name(deco))
                    d_args = tuple(_resolve(a, mod()) for a in deco.args)
                    d_kwargs = {k.arg: _resolve(k.value, mod()) for k in deco.keywords}
                    entry["decorator"] = _decorator_allows(factory, d_args, d_kwargs)
                if isinstance(deco, ast.Call):
                    for arg in deco.args:
                        if _call_name(arg) == "RoleFilter" and isinstance(arg, ast.Call):
                            f_args = tuple(_resolve(a, mod()) for a in arg.args)
                            f_kwargs = {k.arg: _resolve(k.value, mod()) for k in arg.keywords}
                            entry.setdefault("role_filter_modes", []).append(
                                _role_filter_modes(f_args, f_kwargs))
            if entry:
                # Ключ без номера строки: иначе любая правка файла двигала бы снимок.
                seen[node.name] = seen.get(node.name, 0) + 1
                suffix = f"#{seen[node.name]}" if seen[node.name] > 1 else ""
                out[f"{rel}::{node.name}{suffix}"] = entry
    return dict(sorted(out.items()))


# ------------------------------------------------- inline-проверки по всему пакету

PACKAGE_DIRS = ("uk_management_bot", "access_control")
KNOWN_ROLES = frozenset({
    "applicant", "executor", "manager", "inspector", "admin", "system_admin",
    "security_operator", "resource_meter_entry",
})


def _role_constants(node: ast.AST) -> set[str]:
    return {c.value for c in ast.walk(node)
            if isinstance(c, ast.Constant) and c.value in KNOWN_ROLES}


def _role_literals(node: ast.AST) -> set[str]:
    """Имена ролей, по которым принимается решение внутри узла.

    Ловит три формы:
      * сравнения: `"manager" in roles`, `role == "admin"`, `r in ("admin", "manager")`;
      * итерируемое генератора: `any(r in roles for r in ["manager", "admin"])`;
      * пересечение множеств: `{"manager", "admin"} & set(roles)`.
    """
    found: set[str] = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Compare):
            for part in [sub.left, *sub.comparators]:
                found |= _role_constants(part)
        elif isinstance(sub, ast.comprehension) and isinstance(sub.iter, (ast.List, ast.Tuple, ast.Set)):
            found |= _role_constants(sub.iter)
        elif isinstance(sub, ast.BinOp) and isinstance(sub.op, (ast.BitAnd, ast.BitOr, ast.Sub)):
            for side in (sub.left, sub.right):
                if isinstance(side, (ast.Set, ast.List, ast.Tuple)):
                    found |= _role_constants(side)
    return found


def _iter_source_files() -> Iterable[Path]:
    for top in PACKAGE_DIRS:
        for path in sorted((ROOT / top).rglob("*.py")):
            rel = path.relative_to(ROOT).as_posix()
            if (path.name.startswith("test_") or path.name == "conftest.py"
                    or "/tests/" in rel or "/migrations/" in rel):
                continue
            yield path


def snapshot_inline_checks() -> dict[str, Any]:
    """Функции, сравнивающие роль со строкой-именем прямо в теле.

    Две разные природы таких сравнений:
      * решение о правах того, кто действует (`"manager" in roles` перед
        операцией) — переводится на действия;
      * доменное правило о человеке-объекте («назначить можно только
        исполнителя», допустимые роли инвайта) — роль здесь атрибут, не право,
        и остаётся сравнением.
    Это инвентарь, а не матрица: снаружи такие ветвления не вычислить. Тест —
    двунаправленный ратчет: новых сравнений нет, убранные снимают из файла.
    """
    out: dict[str, Any] = {}
    for path in _iter_source_files():
        rel = path.relative_to(ROOT).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"))
        seen: dict[str, int] = {}
        # Только функции верхнего уровня и методы: вложенные учтены в родителе.
        candidates: list[ast.AST] = []
        for top in tree.body:
            if isinstance(top, (ast.FunctionDef, ast.AsyncFunctionDef)):
                candidates.append(top)
            elif isinstance(top, ast.ClassDef):
                candidates.extend(n for n in top.body
                                  if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)))
        for func in candidates:
            roles = sorted(_role_literals(func))
            if not roles:
                continue
            seen[func.name] = seen.get(func.name, 0) + 1
            suffix = f"#{seen[func.name]}" if seen[func.name] > 1 else ""
            out[f"{rel}::{func.name}{suffix}"] = roles
    return dict(sorted(out.items()))


# ------------------------------------------------------------------------- CLI

SNAPSHOTS: dict[str, Callable[[], dict[str, Any]]] = {
    "core_api": snapshot_core_api,
    "access_api": snapshot_access_api,
    "bot_handlers": snapshot_bot,
    "inline_checks": snapshot_inline_checks,
}


def build(name: str) -> dict[str, Any]:
    if name == "inline_checks":  # инвентарь не зависит от профилей
        return {"entries": SNAPSHOTS[name]()}
    return {
        "_profiles": {p.name: {"roles": list(p.roles), "status": p.status} for p in PROFILES},
        "entries": SNAPSHOTS[name](),
    }


def baseline_path(name: str) -> Path:
    return BASELINE_DIR / f"{name}.json"


def dump(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, indent=1, sort_keys=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", action="store_true")
    parser.add_argument("names", nargs="*", default=list(SNAPSHOTS))
    args = parser.parse_args(argv)
    # Отказы гейтов логируются WARNING-ом на каждый профиль — шум, не сигнал.
    logging.disable(logging.WARNING)

    failed = []
    for name in args.names:
        text = dump(build(name))
        path = baseline_path(name)
        if args.write:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
            print(f"записан {path.relative_to(ROOT)}")
        elif not path.exists() or path.read_text(encoding="utf-8") != text:
            failed.append(name)
    if failed:
        print("Снимок прав изменился: " + ", ".join(failed)
              + " — это изменение полномочий; сверить и оформить отдельно.")
        return 1
    if args.check:
        print("OK: матрица прав совпадает со снимком")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
