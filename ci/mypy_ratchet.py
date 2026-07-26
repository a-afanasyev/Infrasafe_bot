#!/usr/bin/env python3
"""AUD5-PRAC-5: ratchet поверх advisory-mypy — счётчик ошибок не должен расти.

Полное внедрение mypy на нетипизированном коде — многонедельная работа, поэтому
джоба остаётся advisory по СОДЕРЖАНИЮ (конкретные ошибки не блокируют мерж). Но
без гейта на КОЛИЧЕСТВО «advisory» означает «растёт незаметно», и именно это
произошло: в бэклоге зафиксировано 3118 ошибок, фактический замер 2026-07-26 дал
3356 — +238 приехали мимо всякого сигнала.

Контракт:
  * текущее число > baseline  → exit 1 (регресс типизации виден и блокирует);
  * текущее < baseline        → exit 0 + громкое напоминание опустить baseline.
    Улучшение НЕ красит CI намеренно: гейт не должен наказывать за попутно
    исправленные две ошибки в чужом PR — та же логика, что у coverage-floor'ов
    рядом («поднимать по мере роста, не опускать»);
  * равно                     → exit 0.

Запуск: mypy ... | python3 ci/mypy_ratchet.py
Baseline: ci/mypy-baseline.txt (одно число).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

BASELINE_FILE = Path(__file__).with_name("mypy-baseline.txt")
# Итоговая строка mypy: "Found 3356 errors in 168 files (checked 341 source files)"
# либо "Success: no issues found in N source files".
_FOUND = re.compile(r"^Found (\d+) errors? in \d+ files?", re.M)
_SUCCESS = re.compile(r"^Success: no issues found", re.M)


def parse_count(output: str) -> int:
    m = _FOUND.search(output)
    if m:
        return int(m.group(1))
    if _SUCCESS.search(output):
        return 0
    raise SystemExit(
        "mypy-ratchet: в выводе нет итоговой строки 'Found N errors' / 'Success'.\n"
        "Скорее всего mypy упал до проверки (коллизия имён пакетов, битый флаг) —\n"
        "это надо чинить, а не считать нулём ошибок."
    )


def main() -> int:
    output = sys.stdin.read()
    # Вывод mypy полезен в логах целиком: ratchet гейтит число, но конкретные
    # ошибки — та самая advisory-ценность, ради которой джоба существует.
    sys.stdout.write(output)

    current = parse_count(output)
    baseline = int(BASELINE_FILE.read_text(encoding="utf-8").split()[0])

    if current > baseline:
        print(
            f"\n✖ mypy-ratchet: ошибок {current}, baseline {baseline} (+{current - baseline}).\n"
            "  Типизация деградировала. Либо исправить новые ошибки, либо — если рост\n"
            "  осознан и обоснован — поднять baseline в этом же PR с объяснением.",
            file=sys.stderr,
        )
        return 1

    if current < baseline:
        print(
            f"\n⚠ mypy-ratchet: ошибок {current}, baseline {baseline} ({baseline - current} исправлено).\n"
            f"  Опусти baseline: echo {current} > ci/mypy-baseline.txt — пока он выше\n"
            "  фактического, гейт разрешает откат к прежнему уровню.",
            file=sys.stderr,
        )
        return 0

    print(f"\n✓ mypy-ratchet: {current} ошибок, ровно baseline.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
