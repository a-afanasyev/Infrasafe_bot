"""Инвентарь object-access API (PR III аудита 2026-08-18).

Каждый эндпоинт с id объекта в path обязан либо нести auth-зависимость, либо
быть в BASELINE с письменным обоснованием. Новый не-manager-only эндпоинт с
path-параметром БЕЗ проверки доступа ломает этот тест.

Пересчёт при ревью плана: из ~69 эндпоинтов с path-параметром не-manager-only
десять; восемь защищены (`get_current_user`/`require_roles` +
`check_request_access`/ownership), два — публичные ПО ЗАМЫСЛУ (T8, docstring
«NO authentication»). Для публичных ратчет пиннит не auth, а IDOR-инварианты —
они уже закреплены поведенчески:
  * не-published → 404: tests/api/test_work_reports_public.py::
    test_media_404_for_non_published_status, test_feed_only_published_visible
  * чужая media вне опубликованной пары невидима: ::test_media_404_cross_report_media_id_idor
"""
from __future__ import annotations

import ast
from pathlib import Path

API_DIR = Path(__file__).resolve().parents[2] / "uk_management_bot" / "api"

# Признаки авторизации в сигнатуре/декораторе (широкие намеренно: задача —
# выдать кандидатов без ЕДИНОГО признака; точечную семантику пиннят
# поведенческие тесты соответствующих роутеров).
AUTH_MARKERS = (
    "get_current_user", "require_roles", "current_user", "require_",
    "verify", "service_token", "api_key", "authenticate", "principal",
    "board_token", "hmac",
)
HTTP_METHODS = {"get", "post", "put", "patch", "delete", "websocket"}

# BASELINE: эндпоинты с id объекта в path БЕЗ auth-зависимости.
# Формат: (относительный путь, имя функции): обоснование.
PUBLIC_BY_DESIGN = {
    ("work_reports/public_router.py", "get_public_work_report"):
        "T8: публичное табло работ; гейт — status=='published' (404 иначе)",
    ("work_reports/public_router.py", "get_public_work_report_media"):
        "T8: media только из опубликованной пары (report_id, media_id)",
}


def _module_auth_aliases(tree: ast.AST) -> set[str]:
    """Локальные алиасы auth-зависимостей: `_manager_only = require_roles(...)`.

    Без них скан ложно считает «голым» эндпоинт с `Depends(_manager_only)` —
    ровно так первая версия записала 22 защищённых эндпоинта в кандидаты.
    """
    aliases: set[str] = set()
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Assign) and node.targets
                and isinstance(node.targets[0], ast.Name)):
            continue
        value_src = ast.unparse(node.value).lower()
        if any(m in value_src for m in AUTH_MARKERS):
            aliases.add(node.targets[0].id.lower())
    return aliases


def _endpoints_with_path_params():
    out = []
    for path in sorted(API_DIR.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        aliases = _module_auth_aliases(tree)
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            route = None
            for deco in fn.decorator_list:
                if (isinstance(deco, ast.Call) and isinstance(deco.func, ast.Attribute)
                        and deco.func.attr in HTTP_METHODS and deco.args
                        and isinstance(deco.args[0], ast.Constant)):
                    route = deco
                    break
            if route is None:
                continue
            url = route.args[0].value
            if "{" not in str(url):
                continue
            blob = (ast.unparse(fn.args) + " " + ast.unparse(route)).lower()
            has_auth = (any(m in blob for m in AUTH_MARKERS)
                        or any(a in blob for a in aliases))
            out.append((str(path.relative_to(API_DIR)), fn.name, has_auth))
    return out


def test_every_object_endpoint_has_auth_or_baseline_entry():
    rows = _endpoints_with_path_params()
    assert rows, "AST-скан не нашёл ни одного эндпоинта — сломан сам скан"

    naked = {(rel, name) for rel, name, has_auth in rows if not has_auth}
    unexpected = naked - set(PUBLIC_BY_DESIGN)
    assert not unexpected, (
        f"Эндпоинты с id объекта БЕЗ auth-зависимости вне BASELINE: {sorted(unexpected)}. "
        f"Либо добавьте авторизацию, либо (для осознанно публичного) запись в "
        f"PUBLIC_BY_DESIGN с обоснованием И поведенческий IDOR-тест."
    )

    # двунаправленность: запись BASELINE без живого эндпоинта тоже красная
    stale = set(PUBLIC_BY_DESIGN) - naked
    assert not stale, f"BASELINE ссылается на исчезнувшие/защищённые эндпоинты: {sorted(stale)}"


def test_scanner_detects_synthetic_offender(tmp_path):
    """Самозащита: скан ловит новый эндпоинт с path-параметром без auth."""
    mod = tmp_path / "synthetic_router.py"
    mod.write_text(
        "@router.get('/things/{thing_id}')\n"
        "async def get_thing(thing_id: int, db=Depends(get_db)):\n    ...\n"
    )
    tree = ast.parse(mod.read_text())
    fn = next(n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef))
    blob = ast.unparse(fn.args).lower()
    assert not any(m in blob for m in AUTH_MARKERS)


def test_public_idor_invariants_are_behaviorally_pinned():
    """Публичные записи BASELINE обязаны иметь живые поведенческие IDOR-тесты."""
    public_tests = Path(__file__).parent / "test_work_reports_public.py"
    src = public_tests.read_text(encoding="utf-8")
    for required in (
        "test_media_404_for_non_published_status",
        "test_media_404_cross_report_media_id_idor",
        "test_feed_only_published_visible",
    ):
        assert f"async def {required}" in src, (
            f"IDOR-инвариант публичного периметра потерял тест {required}"
        )
