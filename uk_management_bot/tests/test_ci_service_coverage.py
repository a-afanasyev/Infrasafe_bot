"""SSOT-гейт: каждый образ из compose собирается в CI, каждый python-сервис — под bandit и pip-audit.

AUD7-ENG-04: у payment_control были тесты и drift-гейт в своём workflow, но
в общей CI его не было ни в перечислении bandit, ни в pip-audit, ни в
images-build — пробел заметил только внешний аудит. До него так же
«за бортом» побывали media_service (AUD5-PRAC-2) и resource (AUD6-P1-1):
списки сервисов в ci.yml правятся руками и отстают от compose.

Источник истины — секции `build:` compose-файлов обоих продов: что
раскатывается, то и проверяется. Гейт статический (парсит YAML и
Dockerfile'ы), работает в обоих наборах; внутри образа без `.github` — skip.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
COMPOSE_FILES = (
    "docker-compose.yml",
    "docker-compose.profk.yml",
    "docker-compose.media.yml",
    "docker-compose.payments.yml",
)


class _ComposeLoader(yaml.SafeLoader):
    """Compose-теги `!override`/`!reset` (docker-compose.profk.yml) — как обычные узлы."""


def _construct_plain(loader: yaml.SafeLoader, node: yaml.Node):
    if isinstance(node, yaml.MappingNode):
        return loader.construct_mapping(node)
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node)
    return loader.construct_scalar(node)


for _tag in ("!override", "!reset"):
    _ComposeLoader.add_constructor(_tag, _construct_plain)


def _compose_dockerfiles() -> set[Path]:
    """Repo-relative пути всех Dockerfile'ов, которые compose собирает."""
    found: set[Path] = set()
    for name in COMPOSE_FILES:
        data = yaml.load((REPO_ROOT / name).read_text(), Loader=_ComposeLoader)  # noqa: S506 — SafeLoader-наследник
        for service in (data.get("services") or {}).values():
            build = (service or {}).get("build")
            if build is None:
                continue
            if isinstance(build, str):
                context, dockerfile = build, "Dockerfile"
            else:
                context = build.get("context", ".")
                dockerfile = build.get("dockerfile", "Dockerfile")
            found.add(Path(context, dockerfile).relative_to("."))
    return found


def _is_python_image(dockerfile: Path) -> bool:
    return (
        re.search(r"^FROM\s+python", (REPO_ROOT / dockerfile).read_text(), re.M)
        is not None
    )


def _python_service_dirs(dockerfiles: set[Path]) -> set[Path]:
    """Каталог сервиса = каталог Dockerfile'а (корневые Dockerfile'ы бота/api/access —
    в корне, их исходники перечислены в bandit явно, см. test ниже)."""
    return {
        d.parent for d in dockerfiles if _is_python_image(d) and d.parent != Path(".")
    }


def _ci() -> dict:
    if not CI_WORKFLOW.exists():
        pytest.skip(f"{CI_WORKFLOW} отсутствует (запуск внутри образа, не чекаут)")
    return yaml.safe_load(CI_WORKFLOW.read_text())


def _steps(ci: dict, job: str) -> list[dict]:
    return ci["jobs"][job]["steps"]


def _bandit_targets(run: str) -> set[str]:
    """Каталоги после `bandit -r` до первого флага (перенос строки через `\\`)."""
    tokens = run.replace("\\\n", " ").split()
    start = tokens.index("-r", tokens.index("bandit")) + 1
    targets: set[str] = set()
    for tok in tokens[start:]:
        if tok.startswith("-"):
            break
        targets.add(tok)
    return targets


def _covered_by(dirname: Path, targets: set[str]) -> bool:
    return any(dirname == Path(t) or Path(t) in dirname.parents for t in targets)


@pytest.fixture(scope="module")
def dockerfiles() -> set[Path]:
    files = _compose_dockerfiles()
    assert files, "compose без единой секции build — поправь гейт"
    return files


def test_every_compose_image_is_built_in_ci(dockerfiles):
    ci = _ci()
    built = {
        Path(step["with"]["file"])
        for step in _steps(ci, "images-build")
        if isinstance(step.get("with"), dict) and "file" in step["with"]
    }
    missing = sorted(str(d) for d in dockerfiles - built)
    assert not missing, (
        "Dockerfile из compose не собирается джобой images-build (.github/workflows/ci.yml): "
        f"{missing}"
    )


def test_bandit_scans_every_python_service(dockerfiles):
    ci = _ci()
    runs = [s["run"] for s in _steps(ci, "bandit") if "bandit -r" in s.get("run", "")]
    assert len(runs) == 2, "ожидались два шага bandit (blocking + advisory)"
    blocking, advisory = (_bandit_targets(r) for r in runs)
    assert blocking == advisory, (
        f"списки bandit разошлись: {sorted(blocking ^ advisory)}"
    )
    expected = {
        Path("uk_management_bot"),
        Path("access_control"),
    } | _python_service_dirs(dockerfiles)
    missing = sorted(str(d) for d in expected if not _covered_by(d, blocking))
    assert not missing, f"python-сервисы вне bandit в ci.yml: {missing}"


def test_pip_audit_covers_every_requirements_file(dockerfiles):
    ci = _ci()
    audited = {
        m.group(1)
        for s in _steps(ci, "pip-audit")
        for m in re.finditer(r"pip-audit\s+-r\s+(\S+)", s.get("run", ""))
    }
    expected = {"requirements.txt"} | {
        str(d / "requirements.txt")
        for d in _python_service_dirs(dockerfiles)
        if (REPO_ROOT / d / "requirements.txt").exists()
    }
    missing = sorted(expected - audited)
    assert not missing, f"requirements без pip-audit в ci.yml: {missing}"


def test_every_python_service_installs_from_hashed_lock(dockerfiles):
    """AUD7-ENG-03: у каждого python-сервиса свой lock с хэшами (как корневой
    requirements.txt: `uv pip compile … --generate-hashes`), и Dockerfile
    ставит зависимости из него, а не из floor-диапазонов/pyproject."""
    problems: list[str] = []
    for service_dir in sorted(_python_service_dirs(dockerfiles)):
        lock = REPO_ROOT / service_dir / "requirements.txt"
        if not lock.exists():
            problems.append(f"{service_dir}: нет requirements.txt (lock)")
            continue
        if "--hash=sha256:" not in lock.read_text():
            problems.append(f"{service_dir}/requirements.txt: без --hash — это не lock")
        dockerfile = next(d for d in dockerfiles if d.parent == service_dir)
        if "-r requirements.txt" not in (REPO_ROOT / dockerfile).read_text():
            problems.append(f"{dockerfile}: pip install не из requirements.txt")
    assert not problems, "\n".join(problems)
