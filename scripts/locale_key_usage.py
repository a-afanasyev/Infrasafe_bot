#!/usr/bin/env python3
"""A9-P3-16: анализ использования ключей локалей бота (ru.json / uz.json).

Ключ считается ЖИВЫМ, если выполняется хоть одно:

* literal  — полное имя ключа встречается как токен в любом отслеживаемом
  git-файле кода/конфигурации (Python: строковые константы и константные
  части f-строк через ``ast``; прочие файлы — токены ``[\\w.]+``). Тесты
  считаются ссылками (удалённый ключ уронил бы тест). ``docs/`` и ``*.md``
  не считаются: упоминание в документации ≠ использование в рантайме;
* dynamic  — ключ подпадает под шаблон, собранный в коде динамически:
  f-строка / конкатенация / ``"...{}".format`` / ``%``, чьи константные
  части похожи на ключ (``f"specializations.{spec}"`` → ``specializations\\.[\\w.]+``),
  либо строковая константа-префикс, оканчивающаяся на ``.``/``_``
  (``KEY = "elevators.bot."``) — всё под ней живое;
* manual   — префиксы из ``MANUAL_DYNAMIC_PREFIXES`` (шаблоны, которые
  начинаются с переменной и не разрешаются статически; сверены вручную —
  скрипт печатает такие шаблоны прод-кода как «unresolved»);
* plural   — ``<ключ>_plural`` / ``<ключ>_plural_many`` живого базового ключа
  (``get_text(..., count=)`` выводит их сам).

Остальное — мёртвое. ``--apply`` удаляет мёртвые ключи из обоих файлов
(пустые после удаления секции тоже), сохраняя порядок ключей.

Запуск: ``python3 scripts/locale_key_usage.py [--apply] [--list]``.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCALES = ROOT / "uk_management_bot" / "config" / "locales"
LOCALE_FILES = ("ru.json", "uz.json")

CODE_SUFFIXES = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".json", ".yml", ".yaml",
    ".sh", ".sql", ".html", ".toml", ".ini", ".cfg", ".txt", ".jsonl",
}
EXCLUDED_PREFIXES = ("docs/",)

KEY_CHARS = re.compile(r"[\w.]+")
TOKEN_RE = re.compile(r"[\w.]+")
HOLE = "\x00"

# Шаблоны, начинающиеся с переменной (f"{prefix}.{x}"), разрешённые вручную.
# Ключ — префикс ключей, значение — где собирается.
MANUAL_DYNAMIC_PREFIXES: dict[str, str] = {}


def flatten(tree: dict, prefix: str = "") -> dict[str, str]:
    out: dict[str, str] = {}
    for k, v in tree.items():
        if isinstance(v, dict):
            out.update(flatten(v, f"{prefix}{k}."))
        else:
            out[f"{prefix}{k}"] = v
    return out


def tracked_files() -> list[Path]:
    names = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, check=True, capture_output=True
    ).stdout.decode().split("\0")
    files = []
    for name in names:
        if not name or name.startswith(EXCLUDED_PREFIXES):
            continue
        path = ROOT / name
        if path.parent == LOCALES or path.suffix not in CODE_SUFFIXES:
            continue
        if path.is_file():
            files.append(path)
    return files


def _parts(node: ast.AST) -> list[str] | None:
    """Константные части выражения-строки; HOLE на месте переменной."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, ast.JoinedStr):
        out: list[str] = []
        for v in node.values:
            if isinstance(v, ast.Constant) and isinstance(v.value, str):
                out.append(v.value)
            else:
                out.append(HOLE)
        return out
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = _parts(node.left), _parts(node.right)
        return (left or [HOLE]) + (right or [HOLE])
    return None


def _format_holes(text: str) -> str:
    """``"a.{}"``/``"a.{x}"``/``"a.%s"`` → ``"a." + HOLE``."""
    text = re.sub(r"\{[^{}]*\}", HOLE, text)
    return re.sub(r"%[sd]", HOLE, text)


def is_test_file(path: Path) -> bool:
    rel = path.relative_to(ROOT).as_posix()
    return rel.startswith("tests/") or "/tests/" in rel or path.name.startswith("test_")


def collect_python(
    path: Path, literals: set[str], templates: set[str], constants: set[str]
) -> None:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError) as exc:
        raise SystemExit(f"не разобрать {path}: {exc}") from exc
    fstring_parts = {
        id(v) for node in ast.walk(tree) if isinstance(node, ast.JoinedStr) for v in node.values
    }
    for node in ast.walk(tree):
        if id(node) in fstring_parts:
            continue  # константная часть f-строки — учтена шаблоном f-строки
        parts = _parts(node)
        if parts is None:
            continue
        if parts == [parts[0]] and parts[0] != HOLE:
            value = parts[0]
            literals.update(TOKEN_RE.findall(value))
            templates.add(_format_holes(value))
            if not is_test_file(path):
                # тесты проверяют «ключ не протёк» через startswith("admin.") — не префикс
                constants.add(value)
            continue
        joined = "".join(parts)
        literals.update(TOKEN_RE.findall(joined.replace(HOLE, " ")))
        templates.add(joined)


def collect_text(path: Path, literals: set[str]) -> None:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return
    literals.update(TOKEN_RE.findall(text))


def template_regexes(templates: set[str], keys: list[str]) -> tuple[list[re.Pattern], list[str]]:
    """Ключеподобные шаблоны → регэкспы; начинающиеся с дыры — на ручной разбор."""
    roots = {k.split(".", 1)[0] for k in keys}
    regexes: list[re.Pattern] = []
    unresolved: list[str] = []
    for tpl in templates:
        if HOLE not in tpl:
            continue
        consts = [c for c in tpl.split(HOLE)]
        if not all(KEY_CHARS.fullmatch(c) or c == "" for c in consts):
            continue
        if "." not in "".join(consts):
            continue
        if tpl.startswith(HOLE):
            unresolved.append(tpl.replace(HOLE, "{…}"))
            continue
        if consts[0].split(".", 1)[0] not in roots:
            continue
        pattern = r"[\w.]+".join(re.escape(c) for c in consts)
        regexes.append(re.compile(pattern))
    return regexes, sorted(set(unresolved))


def prefix_constants(literal_values: set[str], keys: list[str]) -> set[str]:
    """Константы вида ``"elevators.bot."`` — префиксы, по которым ключ собирают.

    ``"x_"`` без точки — это callback-префиксы (``"request_"``, ``"shift_"``),
    не пространство ключей; префикс с ``_`` принимается только внутри секции.
    """
    key_set = set(keys)
    out = set()
    for value in literal_values:
        if len(value) < 3 or value in key_set:
            continue
        if not (value.endswith(".") or (value.endswith("_") and "." in value)):
            continue
        if not KEY_CHARS.fullmatch(value):
            continue
        if any(k.startswith(value) for k in keys):
            out.add(value)
    return out


def analyse() -> dict:
    ru = flatten(json.loads((LOCALES / "ru.json").read_text(encoding="utf-8")))
    keys = list(ru)
    literals: set[str] = set()
    templates: set[str] = set()
    prod_templates: set[str] = set()
    constants: set[str] = set()
    for path in tracked_files():
        if path.suffix == ".py":
            found: set[str] = set()
            collect_python(path, literals, found, constants)
            templates |= found
            if not is_test_file(path):
                prod_templates |= found
        else:
            collect_text(path, literals)

    regexes, _ = template_regexes(templates, keys)
    # На ручной разбор — только прод-код: в тестах «{x}.{y}» — это пути модулей.
    _, unresolved = template_regexes(prod_templates, keys)
    prefixes = prefix_constants(constants, keys) | set(MANUAL_DYNAMIC_PREFIXES)

    live_literal, live_dynamic, dead = [], [], []
    for key in keys:
        if key in literals:
            live_literal.append(key)
        elif any(key.startswith(p) for p in prefixes) or any(r.fullmatch(key) for r in regexes):
            live_dynamic.append(key)
        else:
            dead.append(key)

    live = set(live_literal) | set(live_dynamic)
    plural = [k for k in dead if re.sub(r"_plural(_many)?$", "", k) in live and k.endswith(("_plural", "_plural_many"))]
    dead = [k for k in dead if k not in set(plural)]
    return {
        "total": len(keys),
        "live_literal": live_literal,
        "live_dynamic": live_dynamic,
        "live_plural": plural,
        "dead": dead,
        "dynamic_prefixes": sorted(prefixes),
        "dynamic_patterns": sorted(r.pattern for r in regexes),
        "unresolved_templates": unresolved,
    }


def prune(tree: dict, dead: set[str], prefix: str = "") -> dict:
    out = {}
    for k, v in tree.items():
        full = f"{prefix}{k}"
        if isinstance(v, dict):
            sub = prune(v, dead, f"{full}.")
            if sub or not v:  # секцию, опустевшую из-за чистки, убираем; исходно пустую не трогаем
                out[k] = sub
        elif full not in dead:
            out[k] = v
    return out


def apply(dead: list[str]) -> None:
    dead_set = set(dead)
    for name in LOCALE_FILES:
        path = LOCALES / name
        tree = json.loads(path.read_text(encoding="utf-8"))
        pruned = prune(tree, dead_set)
        path.write_text(json.dumps(pruned, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="удалить мёртвые ключи из ru/uz")
    parser.add_argument("--list", action="store_true", help="напечатать мёртвые ключи")
    args = parser.parse_args()

    result = analyse()
    print(f"total:               {result['total']}")
    print(f"live (literal):      {len(result['live_literal'])}")
    print(f"live (dynamic):      {len(result['live_dynamic'])}")
    print(f"live (plural form):  {len(result['live_plural'])}")
    print(f"dead:                {len(result['dead'])}")
    print("dynamic prefixes:    " + ", ".join(result["dynamic_prefixes"]))
    print("dynamic patterns:    " + ", ".join(result["dynamic_patterns"]))
    if result["unresolved_templates"]:
        print("unresolved (manual): " + ", ".join(result["unresolved_templates"]))
    if args.list:
        print("\n".join(result["dead"]))
    if args.apply:
        apply(result["dead"])
        print(f"удалено {len(result['dead'])} ключей из {', '.join(LOCALE_FILES)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
