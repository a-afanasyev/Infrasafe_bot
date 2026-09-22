"""A9-P2-2 — гейт «сырой пользовательский ввод в HTML-сообщении бота».

Класс BUG-174/178: бот шлёт с ``parse_mode=HTML`` по умолчанию
(``utils/telegram_client.build_bot(html=True)``), и свободный текст из БД
(описание/адрес/примечания заявки, имя и username из Telegram-профиля,
комментарии), подставленный без ``html.escape``, даёт stored-инъекцию разметки
(``<a href>`` — живая ссылка в карточке менеджера), а одиночный ``<``/``&`` —
Telegram-400: менеджер вообще не может открыть заявку.

Канон — экранировать В ТОЧКЕ ВЫВОДА (в БД хранится сырой текст). Гейт — AST:
«заражённое» выражение внутри подстановки сообщения обязано иметь предка
``html.escape(...)``/``escape(...)``.

  * заражённое = атрибут из ``_TAINTED_ATTRS`` (``request.address``,
    ``user.first_name`` …); вызов хелпера, возвращающего сырой текст
    пользователя (``display_name``/``full_name``/``localize_address``/
    ``apartment_address``); ``d.get("<ключ>")``/``d["<ключ>"]`` с ключом из
    ``_TAINTED_KEYS``; локальная переменная, которой последним ДО этой строки
    присвоено заражённое выражение без escape (``x = u.first_name`` → ``{x}``
    нарушение; ``x = html.escape(...)`` снимает заражение);
  * строка с маркером ``# html-raw: <причина>`` пропускается — только для
    значений, которые уходят в БД (notes/audit), а не в Telegram;
  * результат произвольного вызова аргументами не заражается (кроме
    сквозных ``str``/``join``/``strip``…) — поля DTO ловятся по имени
    атрибута (``res.user_name``, ``res.manager_comment``);
  * подстановка = kwarg вызова ``.format(...)``/``get_text(...)`` или
    ``{...}`` в f-строке. Не HTML и не проверяются: аргументы ``logger.*``,
    ``InlineKeyboardButton``/``KeyboardButton``/``builder.button``, текст
    ``raise`` и вызовы с ``show_alert=``
    (всплывашка ``callback.answer`` — простой текст), а также f-строки внутри
    ``html.escape(...)`` (экранированы целиком).

Трассировка локальных переменных — по порядку строк в пределах функции,
без учёта ветвлений (последнее присваивание выше по тексту). Охват —
ГЛОБАЛЬНЫЙ: все модули ``handlers/**``, ``services/**`` и ``utils/**`` (кроме тестов), без
baseline и allowlist-файлов.
"""
from __future__ import annotations

import ast
import pathlib
import re

import pytest

BOT_ROOT = pathlib.Path(__file__).resolve().parent.parent

#: Глобальный охват: все модули бота, кроме тестов. Без baseline/allowlist.
_SCAN_ROOTS = ("handlers", "services", "utils")


def _scanned_modules() -> list[pathlib.Path]:
    paths: list[pathlib.Path] = []
    for root in _SCAN_ROOTS:
        for path in sorted((BOT_ROOT / root).rglob("*.py")):
            rel = path.relative_to(BOT_ROOT)
            if "tests" in rel.parts or path.name.startswith("test_"):
                continue
            paths.append(path)
    return paths


_TAINTED_ATTRS = frozenset({
    "description", "notes", "address", "building_address", "yard_name",
    "first_name", "last_name", "username", "text", "reply_text", "comment",
    "comment_text", "phone", "verification_notes", "completion_report",
    "file_name", "requested_materials", "purchase_materials",
    "manager_materials_comment", "manager_comment", "purchase_history",
    "return_reason", "manager_return_reason",
    # готовые имена в DTO/результатах юнитов
    "user_name", "executor_name", "author_name", "applicant_name",
    "manager_name",
    "title", "reason", "apartment_number", "house_number",
})


#: Служебные поля: тип/идентификатор/счётчик/время — не свободный текст.
_NEVER_TEXT_SUFFIXES = ("_type", "_id", "_ids", "_count", "_at", "_key", "_keys")

#: Системные номера — формирует бот/БД, а не человек. Все прочие ``*_number``
#: (квартира, дом, телефон, лицевой счёт, паспорт, свидетельство, госномер…)
#: считаются вводом. Номер заявки — ``request_number`` и любые
#: ``*_request_number`` (формат YYMMDD-NNN, RequestNumberService).
_SYSTEM_NUMBERS = frozenset({"request_number", "entrance_number",
                             "elevator_number", "next_number", "target_number",
                             "return_to_work_number", "include_number"})


#: Имена, которые по форме «*_name», но несут системный текст (локаль).
_SYSTEM_NAMES = frozenset({"day_name", "spec_name", "status_name", "role_name",
                           "doc_type_name", "document_type_name", "field_name",
                           "file_path", "doc_name"})


def _is_tainted_field(name: str) -> bool:
    """Поле/переменная свободного текста — по имени.

    Кроме явного списка: ``name`` и любые ``*_name`` (material_name,
    template_name, yard_name…), ``comment*``, ``*_reason``, ``*_notes``,
    ``*_address``, ``*_number`` (кроме системных ``_SYSTEM_NUMBERS`` и
    ``*_request_number``), госномер ``plate``/``plate_number*``/``*_plate``.
    """
    if name in _TAINTED_ATTRS:
        return True
    if name.endswith(_NEVER_TEXT_SUFFIXES) or name in _SYSTEM_NAMES \
            or name in _SYSTEM_NUMBERS or name.endswith("_request_number"):
        return False
    return (name in _TAINTED_ATTRS or name == "name" or name.endswith("_name")
            or name.endswith("_number") or name == "plate"
            or name.startswith("plate_number") or name.endswith("_plate")
            or name.startswith("comment") or name.endswith("_reason")
            or name.endswith("_notes") or name.endswith("_address"))
#: Входной текст по имени: ключи словарей/FSM и параметры функций. Шире,
#: чем для локальных переменных: ``status_text``/``message_text`` среди
#: локалей — это собранные сообщения, а ``request_text``/``transfer_comment``
#: на входе функции или в state — ввод человека.
_INPUT_TEXT_NAMES = frozenset({"text", "comment", "reason", "description"})
_INPUT_TEXT_SUFFIXES = ("_text", "_comment", "_reason", "_description")


def _is_tainted_input(name: str | None) -> bool:
    if name is None:
        return False
    return _is_tainted_field(name) or name in _INPUT_TEXT_NAMES \
        or name.endswith(_INPUT_TEXT_SUFFIXES)


_TAINTED_CALLS = frozenset({
    "display_name", "full_name", "localize_address", "apartment_address",
    "_format_employee_name", "_author_name",
})
#: Вызовы, чей результат — это (часть) аргумента: заражение проходит сквозь
#: них. Результат ПРОЧИХ вызовов аргументами не заражается (``run_db(lambda:
#: …message.text…)`` возвращает DTO, а не текст пользователя) — сами
#: заражённые поля DTO ловятся по ``_TAINTED_ATTRS``.
_PASS_THROUGH_CALLS = frozenset({
    "str", "join", "strip", "lstrip", "rstrip", "upper", "lower", "title",
    "capitalize", "replace", "split",
})
_TAINTED_KEYS = frozenset({
    "executor_name", "name", "user_name", "first_name", "last_name",
    "username", "address", "description", "notes", "comment", "yard_name",
    "building_address", "selected_yard_name", "selected_building_address",
})
_NON_HTML_CALLS = frozenset({"InlineKeyboardButton", "KeyboardButton", "button"})
#: Словари локализованных подписей: ключ ``"address"`` там — подпись, не ввод.
_LABEL_DICTS = frozenset({"labels", "locale"})
#: Приведение к числу/булю снимает заражение (``int(message.text)``).
_SAFE_CALLS = frozenset({"escape", "int", "float", "bool", "len", "round"})


def _func_name(call: ast.Call) -> str | None:
    f = call.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        return f.attr
    return None


def _is_escape(call: ast.Call) -> bool:
    return _func_name(call) == "escape"


def _is_safe(call: ast.Call) -> bool:
    return _func_name(call) in _SAFE_CALLS


def _is_non_html_call(call: ast.Call) -> bool:
    """Лог, подписи кнопок и всплывашки Telegram не рендерит как HTML."""
    f = call.func
    if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) \
            and f.value.id in {"logger", "logging", "log"}:
        return True
    if any(kw.arg == "show_alert" for kw in call.keywords):
        return True
    if isinstance(f, ast.Attribute) and f.attr == "answer" \
            and isinstance(f.value, ast.Name) and f.value.id in {"callback", "call", "cb"}:
        return True  # callback.answer — всплывашка, простой текст
    return _func_name(call) in _NON_HTML_CALLS


def _root_name(node: ast.AST) -> str | None:
    while isinstance(node, (ast.Attribute, ast.Subscript, ast.Call)):
        node = node.func if isinstance(node, ast.Call) else node.value
    return node.id if isinstance(node, ast.Name) else None


def _is_tainted_key(key: str | None) -> bool:
    return key is not None and (key in _TAINTED_KEYS or _is_tainted_input(key))


def _const_key(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


class _Taint:
    """Заражённые локальные имена функции: имя → [(строка, заражено?, по имени?)].

    «По имени» — цель распаковки/цикла/параметр: это может быть и строка
    (``first_name``), и объект (``for comment in comments``). Поэтому такое
    имя заражает только САМО себя; ``comment.created_at`` судится по атрибуту.
    """

    def __init__(self) -> None:
        self.history: dict[str, list[tuple[int, bool, bool, bool]]] = {}

    def _last(self, name: str, line: int):  # -> (строка, заражено, по имени, escape)
        last = None
        for entry in self.history.get(name, ()):
            if entry[0] < line:
                last = entry
        return last

    def is_tainted(self, name: str, line: int) -> bool:
        """Заражение «липкое»: ветвления не видны, поэтому чистое
        переприсваивание его НЕ снимает — только значение с html.escape."""
        state = False
        for lineno, tainted, _by_name, escaped in self.history.get(name, ()):
            if lineno >= line:
                break
            if tainted:
                state = True
            elif escaped:
                state = False
        return state

    def is_by_name(self, name: str, line: int) -> bool:
        last = self._last(name, line)
        return bool(last and last[1] and last[2])


def _raw_taints(expr: ast.AST, taint: _Taint | None = None) -> list[ast.AST]:
    """Заражённые узлы expr, у которых нет предка-escape (внутри expr)."""
    found: list[ast.AST] = []

    def visit(node: ast.AST) -> None:
        if isinstance(node, ast.IfExp):
            # условие в текст не попадает — только ветки
            visit(node.body)
            visit(node.orelse)
            return
        if isinstance(node, ast.Call):
            if _is_safe(node):
                return
            name = _func_name(node)
            if name in _TAINTED_CALLS:
                found.append(node)
                return
            if name == "get" and node.args and _is_tainted_key(_const_key(node.args[0])) \
                    and _root_name(node.func) not in _LABEL_DICTS:
                found.append(node)
                return
            if name not in _PASS_THROUGH_CALLS:
                # метод на заражённом значении (``r.notes.strip()``) — через
                # объект метода (имя метода — не поле: ``status.title()``);
                # аргументы произвольного вызова результат не заражают.
                visit(node.func.value if isinstance(node.func, ast.Attribute) else node.func)
                return
            # сквозной вызов: объект метода и аргументы
            visit(node.func.value if isinstance(node.func, ast.Attribute) else node.func)
            for arg in [*node.args, *(kw.value for kw in node.keywords)]:
                visit(arg)
            return
        if isinstance(node, ast.Subscript) and _is_tainted_key(_const_key(node.slice)) \
                and _root_name(node.value) not in _LABEL_DICTS:
            found.append(node)
            return
        if isinstance(node, ast.Attribute):
            if _is_tainted_field(node.attr):
                found.append(node)
                return
            if taint is not None and isinstance(node.value, ast.Name) \
                    and taint.is_by_name(node.value.id, node.lineno):
                return
        if taint is not None and isinstance(node, ast.Name) \
                and isinstance(node.ctx, ast.Load) \
                and taint.is_tainted(node.id, node.lineno):
            found.append(node)
            return
        for child in ast.iter_child_nodes(node):
            visit(child)

    visit(expr)
    return found


def _unpacked_names(target: ast.AST) -> list[str]:
    """Имена из распаковки ``(a, b), c = …`` / ``for a, b in …``."""
    if isinstance(target, ast.Name):
        return [target.id]
    if isinstance(target, (ast.Tuple, ast.List)):
        return [n for elt in target.elts for n in _unpacked_names(elt)]
    if isinstance(target, ast.Starred):
        return _unpacked_names(target.value)
    return []


def _contains_escape(value: ast.AST) -> bool:
    return any(isinstance(n, ast.Call) and _is_escape(n) for n in ast.walk(value))


#: Вызовы, чей результат — заведомо не ввод (подпись/число/текст локали).
_KNOWN_CLEAN_CALLS = frozenset({"get_text", "format", "len", "int", "float",
                                "str", "strftime", "fmt_date", "fmt_time",
                                "fmt_datetime", "join", "escape"})


def _is_opaque_call(value: ast.AST | None) -> bool:
    if isinstance(value, ast.Await):
        value = value.value
    return isinstance(value, ast.Call) and _func_name(value) not in _KNOWN_CLEAN_CALLS \
        and _func_name(value) not in _TAINTED_CALLS


def _collect_taint(scope: ast.AST) -> _Taint:
    """Проход по присваиваниям scope в порядке строк.

    Распаковка кортежа, цель цикла и параметр функции значения не
    показывают — там заражение определяется по ИМЕНИ (``first_name``,
    ``material_name``, ``address``…): ``(first_name, username), docs = page``.
    """
    taint = _Taint()
    assigns: list[tuple[int, list[str], ast.AST | None, bool]] = []
    for node in ast.walk(scope):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = node.args
            for a in [*args.posonlyargs, *args.args, *args.kwonlyargs]:
                if _is_tainted_input(a.arg):
                    assigns.append((node.lineno - 1, [a.arg], None, False))
        elif isinstance(node, (ast.For, ast.AsyncFor, ast.comprehension)):
            lineno = getattr(node, "lineno", None) or node.target.lineno
            names = [n for n in _unpacked_names(node.target) if _is_tainted_field(n)]
            if names:
                assigns.append((lineno, names, None, False))
        elif isinstance(node, ast.Assign):
            names = [t.id for t in node.targets if isinstance(t, ast.Name)]
            assigns.append((node.lineno, names, node.value, False))
            for t in node.targets:
                if isinstance(t, (ast.Tuple, ast.List)):
                    unpacked = [n for n in _unpacked_names(t) if _is_tainted_field(n)]
                    if unpacked:
                        assigns.append((node.lineno, unpacked, None, False))
        elif isinstance(node, ast.AnnAssign) and node.value is not None \
                and isinstance(node.target, ast.Name):
            assigns.append((node.lineno, [node.target.id], node.value, False))
        elif isinstance(node, ast.AugAssign) and isinstance(node.target, ast.Name):
            assigns.append((node.lineno, [node.target.id], node.value, True))
    for lineno, names, value, augmented in sorted(assigns, key=lambda a: a[0]):
        by_name = value is None
        tainted = True if by_name else bool(_raw_taints(value, taint))
        escaped = value is not None and _contains_escape(value)
        for name in names:
            name_taint = tainted
            if not name_taint and not escaped and not augmented \
                    and _is_tainted_field(name) and _is_opaque_call(value):
                # ``address = await run_db(...)``: значение не видно, судим по имени
                name_taint = True
            if augmented:
                name_taint = name_taint or taint.is_tainted(name, lineno)
            taint.history.setdefault(name, []).append(
                (lineno, name_taint, by_name or name_taint and not tainted, escaped))
    return taint


def _substitutions(scope: ast.AST):
    """Выражения-подстановки scope по правилам гейта."""
    skipped: set[int] = set()
    for node in ast.walk(scope):
        # Текст исключения — не сообщение Telegram; показ ошибки экранирует
        # её получатель.
        is_raise = isinstance(node, ast.Raise)
        if is_raise or (isinstance(node, ast.Call)
                        and (_is_non_html_call(node) or _is_escape(node))):
            for sub in ast.walk(node):
                skipped.add(id(sub))

    for node in ast.walk(scope):
        if isinstance(node, ast.Call) and _func_name(node) == "get_text" \
                and node.args and isinstance(node.args[0], ast.JoinedStr):
            for sub in ast.walk(node.args[0]):
                skipped.add(id(sub))  # f-строка — ключ локали, не текст
    for node in ast.walk(scope):
        if id(node) in skipped:
            continue
        if isinstance(node, ast.Call) and _func_name(node) in {"format", "get_text"}:
            for kw in node.keywords:
                if kw.arg not in (None, "language"):
                    yield kw.value
        elif isinstance(node, ast.JoinedStr):
            for part in node.values:
                if isinstance(part, ast.FormattedValue):
                    yield part.value


def _scopes(tree: ast.Module):
    funcs = [n for n in ast.walk(tree)
             if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    # Вложенные функции проверяются в составе внешней (одна область имён
    # на гейт достаточна); модульный уровень — отдельной областью.
    outer = [f for f in funcs
             if not any(f is not g and f in ast.walk(g) for g in funcs)]
    module_level = ast.Module(
        body=[s for s in tree.body
              if not isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))],
        type_ignores=[])
    return [module_level] + outer


#: Маркер строки, где сырой текст законен: значение уходит НЕ в Telegram
#: (запись в БД — notes/audit), экранируется при показе. Причина обязательна.
_RAW_OK = re.compile(r"# html-raw:\s*\S")


def scan_source(source: str, label: str) -> list[str]:
    hits: list[str] = []
    lines = source.splitlines()
    tree = ast.parse(source)
    for scope in _scopes(tree):
        taint = _collect_taint(scope)
        for expr in _substitutions(scope):
            for bad in _raw_taints(expr, taint):
                if _RAW_OK.search(lines[bad.lineno - 1]):
                    continue
                hits.append(f"{label}:{bad.lineno}: {ast.unparse(bad)}")
    return sorted(set(hits))


def test_no_raw_user_input_in_html_messages():
    paths = _scanned_modules()
    assert len(paths) > 100, "охват гейта неожиданно опустел"
    hits: list[str] = []
    for path in paths:
        rel = str(path.relative_to(BOT_ROOT))
        hits += scan_source(path.read_text(encoding="utf-8"), rel)
    assert hits == [], (
        "A9-P2-2 (класс BUG-174/178): сырой пользовательский ввод в "
        "HTML-сообщении бота. Оберните подстановку в html.escape(...) в точке "
        "вывода (данные в БД не экранировать):\n  " + "\n  ".join(hits)
    )


# ── самопроверка гейта на синтетике ─────────────────────────────────────

def _wrap(body: str) -> str:
    if body.startswith("def "):
        return body  # сниппет уже функция — проверяются её параметры
    return "def f():\n" + "\n".join("    " + line for line in body.splitlines())


@pytest.mark.parametrize("snippet", [
    'get_text("k").format(description=request.description)',
    'get_text("k", language=lang, executor_name=f"{u.first_name} {u.last_name}")',
    'text = f"   {label} {request.notes}"',
    'get_text("k").format(address=localize_address(request.address, lang))',
    'get_text("k", executor_name=display_name(executor))',
    'get_text("k").format(reason=r.notes.strip())',
    # локальные переменные
    'name = u.first_name\ntext = f"• {name}"',
    'name = f"{u.first_name} {u.last_name}".strip()\nget_text("k").format(name=name)',
    'name = a.get("executor_name") or "#1"\nlines += f"→ {name}"',
    'name = a["executor_name"]\nget_text("k", name=name)',
    'x = display_name(u)\nmsg = f"{x}"',
    'addr = r.address[:60]\nget_text("k").format(address=addr)',
    # маркер без причины не освобождает
    'note = f"{u.first_name}"  # html-raw:',
    'note = f"{u.first_name}"  # html-raw:   ',
    'res = run_db(lambda s: f(s))\nget_text("k", name=res.user_name)',
    'name = _format_employee_name(e)\ntext = f"{name}"',
    # Кавычки внутри f-строки — другие, чем снаружи: вложенные одинаковые
    # (PEP 701) парсятся только с 3.12, а прод-образ на 3.11.
    "text = f\"{' '.join([u.first_name, u.last_name])}\"",
    'text = f"{label} {request.manager_return_reason}"',
    'address = await run_db(lambda s: load(s))\ntext = get_text("k").format(address=address)',
    'name = ""\nif t:\n    name = t.name\nelif k:\n    name = get_text("x")\ntext = f"{name}"',
    'template_name = data.get("template_name")\ntext = get_text("k", name=template_name)',
    'get_text("access_control.vehicle.created", plate=req.plate_number_normalized)',
    'text += f"• {v.vehicle_plate} — {v.status}"',
    'text = f"{a.account_number}"',
    'comment_val = data.get("transfer_comment", "") or "-"\ntext = get_text("k").format(comment=comment_val)',
    'def build(user, request_text):\n    return f"Комментарий: {request_text}"',
    '(first_name, username), docs = page\nget_text("k").format(name=first_name or username)',
    'for name, qty in rows:\n    text += f"{name}: {qty}"',
    'get_text("k", name=issue.material_name)',
    'text = f"{template.name}"',
    'get_text("k").format(number=apt.apartment_number)',
])
def test_gate_catches_synthetic_violation(snippet):
    assert scan_source(_wrap(snippet), "synthetic"), snippet


@pytest.mark.parametrize("snippet", [
    'get_text("k").format(description=html.escape(request.description or ""))',
    'get_text("k", executor_name=html.escape(display_name(executor)))',
    'text = f"   {label} {html.escape(request.notes)}"',
    'logger.info(f"адрес {request.address}")',
    'get_text("k").format(address=html.escape(localize_address(request.address, lang)))',
    'InlineKeyboardButton(text=f"{icon} {display_name(executor)}", callback_data="x")',
    'username = html.escape(f"@{details.username}")',
    'await callback.answer(get_text("k").format(address=b.address), show_alert=True)',
    # локальные переменные: escape снимает заражение
    'name = html.escape(display_name(u))\ntext = f"• {name}"',
    'name = u.first_name\nname = html.escape(name)\ntext = f"• {name}"',
    'name = a.get("executor_name")\nget_text("k", name=html.escape(name))',
    'count = len(items)\ntext = f"{count}"',
    'state_data = {"address": b.address}',
    'floors = int(message.text)\ntext = f"{floors}"',
    'res = run_db(lambda s: unit(s, message.text))\ntext = f"{res.count}"',
    'raise AddressConflict(f"Двор {updates[\'name\']} уже есть")',
    'builder.button(text=f"{b.address}", callback_data="x")',
    'for i, r in enumerate(rows):\n    text += f"{i}. #{r.request_number}"',
    '(first_name, username), docs = page\nname = html.escape(first_name or username)\ntext = f"{name}"',
    'for comment in comments:\n    text += f"{comment.created_at} {comment.comment_type}"',
    'text = f"{shift.status.title()}"',
    'text = f"#{r.request_number} {r.entrance_number} {data.get(\'comment_request_number\')}"',
    'await callback.answer(get_text("k", name=template_name))',
    'reason_text = get_text(f"shift_transfer.reason_{reason}", language=lang)',
    'for day_name, count in stats.items():\n    text += f"{day_name}: {count}"',
    'address = await run_db(f)\naddress = html.escape(address)\ntext = f"{address}"',
    'text = f"{labels[\'address\']} {html.escape(r.address)}"',
    'text = f"{locale.get(\'requests\', {}).get(\'address\', \'A\')}: x"',
    'u = html.escape(f"@{d.username}") if d.username else "-"\nget_text("k").format(username=u)',
    'note = f"{u.first_name}: {text}"  # html-raw: пишется в notes, не в Telegram',
])
def test_gate_passes_escaped_or_non_html(snippet):
    assert scan_source(_wrap(snippet), "synthetic") == [], snippet
