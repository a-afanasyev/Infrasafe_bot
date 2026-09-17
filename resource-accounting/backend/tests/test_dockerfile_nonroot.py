"""AUD7-ENG-08: образ resource API/worker запускается не от root.

Compose пользователя не переопределяет (docker-compose.yml resource-api/worker,
profk-overlay), поэтому единственная точка — Dockerfile. Гейт статический:
после установки кода объявлен непривилегированный USER, и он стоит ПОСЛЕ
последнего RUN/COPY (иначе шаги сборки, требующие root, упадут, а рантайм
всё равно останется root).
"""
from pathlib import Path

DOCKERFILE = Path(__file__).resolve().parent.parent / "Dockerfile"


def _lines() -> list[str]:
    return [l.strip() for l in DOCKERFILE.read_text(encoding="utf-8").splitlines() if l.strip()]


def test_dockerfile_declares_non_root_user():
    users = [l for l in _lines() if l.startswith("USER ")]
    assert users, "в Dockerfile нет USER — рантайм под root"
    assert users[-1].split()[1] != "root"


def test_user_comes_after_build_steps():
    lines = _lines()
    user_idx = max(i for i, l in enumerate(lines) if l.startswith("USER "))
    late_root_steps = [l for l in lines[user_idx + 1:] if l.startswith(("RUN ", "COPY ", "ADD "))]
    assert late_root_steps == [], late_root_steps
