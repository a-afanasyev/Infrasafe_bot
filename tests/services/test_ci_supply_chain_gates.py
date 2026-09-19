"""AUD8-ENG-03: supply-chain гигиена CI/Docker.

* `uses:` в workflows — только по commit SHA (теги мутабельны; job images-build
  публикует образы с `packages: write`);
* top-level `permissions:` в каждом workflow (GITHUB_TOKEN — минимум);
* базовые образы Dockerfile'ов — по digest (`@sha256:`), как в Dockerfile.api;
* dev-compose не открывает БД/кэш на 0.0.0.0.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
DOCKERFILES = [
    ROOT / "Dockerfile",
    ROOT / "Dockerfile.api",
    ROOT / "Dockerfile.access",
    ROOT / "Dockerfile.dev",
    ROOT / "frontend" / "Dockerfile",
    ROOT / "media_service" / "Dockerfile",
    ROOT / "payment_control" / "Dockerfile",
    ROOT / "resource-accounting" / "backend" / "Dockerfile",
]
_USES = re.compile(r"^\s*-?\s*uses:\s*([^\s#]+)")
_SHA_REF = re.compile(r"^[\w.-]+/[\w.-]+(?:/[\w./-]+)?@[0-9a-f]{40}$")


def test_workflow_actions_pinned_by_commit_sha():
    bad = []
    for wf in WORKFLOWS:
        for n, line in enumerate(wf.read_text(encoding="utf-8").splitlines(), 1):
            m = _USES.match(line)
            if m and not m.group(1).startswith("./") and not _SHA_REF.match(m.group(1)):
                bad.append(f"{wf.name}:{n} {m.group(1)}")
    assert not bad, "actions не по SHA: " + ", ".join(bad)


def test_workflows_declare_top_level_permissions():
    missing = [wf.name for wf in WORKFLOWS if not re.search(r"^permissions:", wf.read_text(encoding="utf-8"), re.M)]
    assert not missing, "нет top-level permissions: " + ", ".join(missing)


def test_dockerfile_base_images_pinned_by_digest():
    bad = []
    for df in DOCKERFILES:
        for n, line in enumerate(df.read_text(encoding="utf-8").splitlines(), 1):
            if line.startswith("FROM ") and "@sha256:" not in line and " AS " not in line.upper().replace("FROM ", "", 1)[:0]:
                image = line.split()[1]
                # `FROM <stage>` (ссылка на свой этап) — не образ.
                if ":" in image or "/" in image:
                    bad.append(f"{df.relative_to(ROOT)}:{n} {image}")
    assert not bad, "базовый образ без digest: " + ", ".join(bad)


def test_dev_compose_binds_db_and_cache_to_loopback():
    text = (ROOT / "docker-compose.dev.yml").read_text(encoding="utf-8")
    exposed = re.findall(r'^\s*-\s*"?(\d+:\d+)"?\s*$', text, re.M)
    assert not exposed, f"dev-compose порты на всех интерфейсах: {exposed}"
