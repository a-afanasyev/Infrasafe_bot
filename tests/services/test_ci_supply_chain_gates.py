"""AUD8-ENG-03: supply-chain гигиена CI/Docker.

* `uses:` в workflows — только по commit SHA (теги мутабельны; job images-build
  публикует образы с `packages: write`);
* top-level `permissions:` в каждом workflow (GITHUB_TOKEN — минимум);
* базовые образы Dockerfile'ов — по digest (`@sha256:`), как в Dockerfile.api;
* A9-P3-26: сторонние образы compose (postgres/redis) — тоже по digest тега;
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
# Все compose-файлы репо (прод-база, оверлеи площадок, dev). Список — глобом,
# чтобы новый оверлей не выпал из гейта молча.
COMPOSE_FILES = sorted(ROOT.glob("docker-compose*.yml"))
_IMAGE = re.compile(r"^\s*image:\s*[\"']?([^\s\"'#]+)")
_DIGEST = re.compile(r"@sha256:[0-9a-f]{64}$")
_USES = re.compile(r"^\s*-?\s*uses:\s*([^\s#]+)")
_SHA_REF = re.compile(r"^[\w.-]+/[\w.-]+(?:/[\w./-]+)?@[0-9a-f]{40}$")
# A9-P2-20: собственные образы registry-режима пиннятся не digest'ом, а тегом
# sha-<полный SHA коммита> — его ставит только images-promote с main после
# зелёного CI; digest на момент коммита compose ещё не существует.
_OWN_SHA_IMAGE = re.compile(r"^ghcr\.io/a-afanasyev/uk-[a-z-]+:sha-\$\{UK_IMAGE_SHA:\?")


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


def test_compose_third_party_images_pinned_by_digest():
    """A9-P3-26: stateful-образы (postgres/redis) плавали по минору между
    деплоями — тег мутабелен. Сторонний образ = ссылка с тегом (`name:tag`);
    локально собираемые (`image: uk-media-service` рядом с `build:`) — без тега,
    их гейт не касается."""
    assert COMPOSE_FILES, "не найдено ни одного docker-compose*.yml"
    bad = []
    for cf in COMPOSE_FILES:
        for n, line in enumerate(cf.read_text(encoding="utf-8").splitlines(), 1):
            m = _IMAGE.match(line)
            if not m:
                continue
            ref = m.group(1)
            if _OWN_SHA_IMAGE.match(ref):
                continue
            name = ref.split("@", 1)[0].rsplit("/", 1)[-1]
            if ":" in name and not _DIGEST.search(ref):
                bad.append(f"{cf.name}:{n} {ref}")
    assert not bad, "образ compose без digest: " + ", ".join(bad)
