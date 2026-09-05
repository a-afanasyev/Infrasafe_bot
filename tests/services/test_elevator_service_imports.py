"""Импорт-гейт пакета «Лифты»: без runner'а и сетевых/фреймворковых стеков.

``set_status(source="request_hint")`` будут вызывать из хендлеров рядом с
``workflow_runner`` — если пакет тянет runner на импорте, цикл гарантирован.
Чистый интерпретатор (subprocess, образец ``test_metadata_completeness.py``):
в общем pytest-процессе runner уже импортирован другими тестами и гейт был бы слеп.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

FORBIDDEN = (
    "uk_management_bot.services.workflow_runner",
    "httpx",
    "aiogram",
    "fastapi",
)

_SNIPPET = (
    "import json, sys\n"
    "import uk_management_bot.services.elevator_service\n"
    "import uk_management_bot.services.elevator_service.grouping\n"
    f"forbidden = {FORBIDDEN!r}\n"
    "print(json.dumps([m for m in forbidden if m in sys.modules]))\n"
)


def _loaded_forbidden_modules() -> list[str]:
    env = dict(os.environ)
    env.setdefault("DATABASE_URL", "sqlite:///test_services.db")
    env.setdefault("DEBUG", "true")
    env.setdefault("INVITE_SECRET", "test_secret_for_unit_tests")
    env.setdefault("ADMIN_PASSWORD", "test_admin_password")
    proc = subprocess.run(
        [sys.executable, "-c", _SNIPPET],
        capture_output=True,
        text=True,
        env=env,
        cwd=os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    )
    assert proc.returncode == 0, (
        f"isolated import failed:\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    )
    return json.loads(proc.stdout.strip().splitlines()[-1])


def test_package_import_does_not_pull_runner_or_frameworks():
    assert _loaded_forbidden_modules() == []
