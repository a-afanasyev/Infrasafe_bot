"""WR-06 (класс) — гейт на unbound `lang` в `except`-блоках хендлеров.

Дефект: `lang = get_user_language(...)` (или `lang = language`) присваивается
ВНУТРИ `try`, причём внутри `with`-блока или после падаемого вызова. Если это
место бросит — до присваивания дело не доходит, и `except` ниже ссылается на
несвязанное имя. Пользователь вместо сообщения об ошибке не получает НИЧЕГО:
вторичный `NameError` уходит в глобальный хендлер как ещё одна ошибка.

Почему гейт, а не только правка. Пункт `WR-06` был сформулирован по одному
пакету (`handlers/shift_management/`) и содержал 4 сайта. AST-скан по ВСЕМ
хендлерам нашёл ещё 16 в пяти других файлах — то есть это класс, а не локальная
небрежность, и без гейта он вернётся с первым же новым хендлером, написанным по
образцу соседнего.

Точность важнее охвата: наивный скан («присваивание внутри try») дал 42
кандидата, из которых больше половины — ложные. `lang = language` первой строкой
`try` упасть не может (параметр всегда связан), значит `except` безопасен.
Поэтому ниже сайт считается дефектным только если до первого присваивания `lang`
уже есть падаемый вызов ИЛИ присваивание вложено (в `with`/`if`/`for`).
"""
import ast
from pathlib import Path

HANDLERS = Path(__file__).resolve().parents[2] / "uk_management_bot" / "handlers"


def _lang_nodes(nodes, ctx):
    return [
        s
        for n in nodes
        for s in ast.walk(n)
        if isinstance(s, ast.Name) and s.id == "lang" and isinstance(s.ctx, ctx)
    ]


def _first_binding_is_safe(try_node: ast.Try) -> bool:
    """`lang` связан на верхнем уровне `try` до любого падаемого вызова."""
    for stmt in try_node.body:
        if _lang_nodes([stmt], ast.Store):
            calls = [c for c in ast.walk(stmt) if isinstance(c, ast.Call)]
            return not calls and isinstance(stmt, (ast.Assign, ast.AnnAssign))
        if any(isinstance(c, ast.Call) for c in ast.walk(stmt)):
            return False
    return False


def _scan() -> list[str]:
    found = []
    for path in sorted(HANDLERS.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for fn in [
            n for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]:
            params = {a.arg for a in fn.args.args} | {a.arg for a in fn.args.kwonlyargs}
            for i, stmt in enumerate(fn.body):
                if not isinstance(stmt, ast.Try):
                    continue
                if "lang" in params or _lang_nodes(fn.body[:i], ast.Store):
                    continue  # дефолт до try — канон
                if _first_binding_is_safe(stmt):
                    continue
                for handler in stmt.handlers:
                    if _lang_nodes(handler.body, ast.Load) and not _lang_nodes(
                        handler.body, ast.Store
                    ):
                        rel = path.relative_to(HANDLERS.parents[1])
                        found.append(f"{rel}:{handler.lineno} ({fn.name})")
    return found


def test_no_unbound_lang_in_except_blocks():
    offenders = _scan()
    assert not offenders, (
        "unbound `lang` в except-блоке: если try бросит до присваивания, "
        "except даст NameError и пользователь не получит вообще ничего.\n"
        "Канон: `lang = \"ru\"` ДО `try` (не переприсваивание внутри except — так "
        "сохраняется реальный язык пользователя, если он уже был определён).\n"
        + "\n".join(f"  {o}" for o in offenders)
    )


def test_scanner_detects_a_synthetic_offender():
    """Гейт без самопроверки — гейт, который может молча ничего не проверять.

    Здесь скан прогоняется по искусственному дефектному коду: если он вернёт
    пусто, значит `test_no_unbound_lang_in_except_blocks` зелен не потому, что
    код чист, а потому что скан сломан.
    """
    src = (
        "async def h(callback, db=None):\n"
        "    try:\n"
        "        with scope() as db:\n"
        "            lang = get_user_language(1, db)\n"
        "    except Exception:\n"
        "        answer(text(language=lang))\n"
    )
    tree = ast.parse(src)
    fn = tree.body[0]
    try_node = fn.body[0]
    assert not _first_binding_is_safe(try_node), (
        "скан считает безопасным присваивание внутри with-блока — он сломан"
    )
    assert _lang_nodes(try_node.handlers[0].body, ast.Load)
    assert not _lang_nodes(try_node.handlers[0].body, ast.Store)


def test_scanner_accepts_safe_first_binding():
    """Обратная сторона: `lang = language` первой строкой try — не дефект."""
    src = (
        "async def h(callback, language='ru'):\n"
        "    try:\n"
        "        lang = language\n"
        "        risky()\n"
        "    except Exception:\n"
        "        answer(text(language=lang))\n"
    )
    try_node = ast.parse(src).body[0].body[0]
    assert _first_binding_is_safe(try_node)
