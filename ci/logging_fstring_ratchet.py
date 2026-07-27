#!/usr/bin/env python3
"""REFACTOR-113: ratchet на eager-f-string в логах — счётчик не должен расти.

Пункт был заведён как «≥50 вхождений, bulk-rewrite через ruff G004 auto-fix».
Замер 2026-07-27 опроверг обе половины формулировки:

  * вхождений **1517**, а не «≥50» — тридцатикратная разница, и она меняет
    характер задачи: это не вычистка, а массовая переписка логов;
  * **автофикса у G004 нет.** Проверено: `ruff check --select G004 --fix
    --unsafe-fixes` оставляет файл без изменений, помощь ограничена подсказкой
    «Convert to lazy % formatting». То есть заявленный способ не существует, а
    настоящий — самописный codemod по 1517 сайтам, где легко испортить
    format-spec (`{x:.2f}`), `!r`, вложенные кавычки и выражения с запятыми.

Поэтому здесь то же решение, что у mypy (`ci/mypy_ratchet.py`): содержание
остаётся advisory, а КОЛИЧЕСТВО под гейтом. Без него «отложено» означает
«растёт незаметно» — ровно это и произошло с самим пунктом (50 → 1517).

Контракт (намеренно совпадает с mypy-ratchet):
  * текущее > baseline → exit 1 (новые eager-f-string в логах видны и блокируют);
  * текущее < baseline → exit 0 + напоминание опустить baseline (улучшение не
    должно красить чужой PR);
  * равно              → exit 0.

Запуск: ruff check --select G004 --exit-zero --output-format=concise . \
          | python3 ci/logging_fstring_ratchet.py
Baseline: ci/logging-fstring-baseline.txt (одно число).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

BASELINE_FILE = Path(__file__).with_name("logging-fstring-baseline.txt")
# concise-строка ruff: "path/to/file.py:12:5: G004 Logging statement uses f-string"
_VIOLATION = re.compile(r"^\S+:\d+:\d+: G004\b", re.M)


def parse_count(output: str) -> int:
    return len(_VIOLATION.findall(output))


def main() -> int:
    output = sys.stdin.read()
    if output.strip() and not _VIOLATION.search(output):
        # Пустой ввод — законный ноль. Непустой без единого совпадения означает,
        # что формат вывода поменялся и мы бы молча считали ноль: это надо
        # чинить, а не пропускать.
        raise SystemExit(
            "logging-fstring-ratchet: вывод непустой, но ни одной строки G004 не\n"
            "распознано — сменился формат `ruff --output-format=concise`?\n"
            f"Первая строка: {output.splitlines()[0]!r}"
        )

    current = parse_count(output)
    baseline = int(BASELINE_FILE.read_text(encoding="utf-8").split()[0])

    if current > baseline:
        print(
            f"\n✖ logging-fstring-ratchet: {current}, baseline {baseline} "
            f"(+{current - baseline}).\n"
            "  В логах появились новые eager-f-string. Писать так:\n"
            '      logger.info("текст %s", var)   # вместо f"текст {var}"\n'
            "  — строка не форматируется, если уровень логирования выключен.",
            file=sys.stderr,
        )
        return 1

    if current < baseline:
        print(
            f"\n⚠ logging-fstring-ratchet: {current}, baseline {baseline} "
            f"({baseline - current} исправлено).\n"
            f"  Опусти baseline: echo {current} > ci/logging-fstring-baseline.txt",
            file=sys.stderr,
        )
        return 0

    print(f"\n✓ logging-fstring-ratchet: {current}, ровно baseline.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
