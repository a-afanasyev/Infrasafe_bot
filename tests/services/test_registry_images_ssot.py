"""A9-P2-20: SSOT-гейт registry-режима деплоя (прод тянет CI-образы из GHCR).

Registry-overlay площадки (`docker-compose.registry.<site>.yml`) подменяет
каждую host-сборку базового набора на `image: ghcr.io/a-afanasyev/<образ>:sha-<SHA>`.
Цепочка держится на трёх списках, которые правятся руками и легко разъезжаются:

* сервисы с `build:` в наборе площадки (base + overlay'и из таблицы SKILL);
* сервисы в registry-overlay'е и имена их образов;
* образы, которые публикует images-build (кандидат `ci-<sha>`) и переводит в
  `sha-<sha>` images-promote.

Забытый сервис молча продолжал бы собираться на хосте (или, при сборке, не
существовал бы в GHCR); лишний сервис в overlay'е compose СОЗДАЛ бы из одного
`image:` (payments-сервис на 105); образ не из того Dockerfile'а — подмена.
Плюс: промоушен обязан ждать ВСЕ job'ы, а флаги фронта registry-образа — совпадать
по набору ключей с `ARG VITE_*` frontend/Dockerfile (новый флаг иначе молча OFF).

Статический (парсит YAML); внутри образа без `.github` — skip, как у
`uk_management_bot/tests/test_ci_service_coverage.py`.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
REGISTRY = "ghcr.io/a-afanasyev"
FLAGS_DIR = ROOT / "deploy" / "frontend-flags"
FRONTEND_DOCKERFILE = ROOT / "frontend" / "Dockerfile"

# Наборы площадок — зеркало таблицы «Площадка → COMPOSE» в
# .claude/skills/uk-deploy/SKILL.md (её сверяет test_deploy_runbook_compose_ssot).
SITES = {
    "profk": ("docker-compose.yml", "docker-compose.profk.yml", "docker-compose.payments.yml"),
    "infrasafe": ("docker-compose.yml", "docker-compose.media.yml"),
}
_RESET = object()
_IMAGE_RE = re.compile(
    r"^ghcr\.io/a-afanasyev/(?P<name>uk-[a-z-]+):sha-\$\{UK_IMAGE_SHA:\?[^}]+\}$"
)
_CI_TAG_RE = re.compile(r"^\$\{\{ env\.REGISTRY \}\}/(?P<name>[\w.-]+):ci-\$\{\{ github\.sha \}\}$")

pytestmark = pytest.mark.skipif(
    not CI_WORKFLOW.exists() or not (ROOT / "docker-compose.registry.profk.yml").exists(),
    reason="запуск внутри образа без .github/compose — гейт гоняется в CI на полном чекауте",
)


class _Loader(yaml.SafeLoader):
    """Compose-теги: `!reset` → маркер удаления, `!override` → обычный узел."""


def _reset(loader: yaml.SafeLoader, node: yaml.Node):
    return _RESET


def _override(loader: yaml.SafeLoader, node: yaml.Node):
    if isinstance(node, yaml.MappingNode):
        return loader.construct_mapping(node)
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node)
    return loader.construct_scalar(node)


_Loader.add_constructor("!reset", _reset)
_Loader.add_constructor("!override", _override)


def _services(name: str) -> dict:
    data = yaml.load((ROOT / name).read_text(encoding="utf-8"), Loader=_Loader)  # noqa: S506 — SafeLoader-наследник
    return data.get("services") or {}


def _build_path(build) -> Path:
    if isinstance(build, str):
        return Path(build, "Dockerfile")
    return Path(build.get("context", "."), build.get("dockerfile", "Dockerfile"))


def _site_builds(site: str) -> dict[str, Path]:
    """service → repo-relative Dockerfile для сервисов, которые набор площадки собирает.

    Мерж упрощённый и опирается на порядок `SITES[site]`: базовый файл первым,
    overlay'и после (как в `-f` таблицы SKILL). `build:` без `context` в overlay'е
    (profk frontend: только args) считается дополнением к уже известной сборке.
    Если такой overlay встретился раньше базы, Dockerfile потерялся бы молча —
    поэтому ниже assert.
    """
    assert SITES[site][0] == "docker-compose.yml", "базовый compose обязан идти первым"
    builds: dict[str, Path | None] = {}
    for name in SITES[site]:
        for svc, spec in _services(name).items():
            spec = spec or {}
            if "build" not in spec:
                builds.setdefault(svc, None)
                continue
            build = spec["build"]
            if build is _RESET:
                builds[svc] = None
            elif isinstance(build, dict) and "context" not in build:
                # override только args (profk frontend) — Dockerfile из базы
                assert builds.get(svc), f"{name}: {svc}.build без context до базовой сборки"
                continue
            else:
                builds[svc] = _build_path(build)
    return {svc: path for svc, path in builds.items() if path is not None}


def _site_service_names(site: str) -> set[str]:
    return {svc for name in SITES[site] for svc in _services(name)}


def _ci() -> dict:
    return yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))


def _published() -> list[tuple[Path, str, dict]]:
    """(Dockerfile, имя образа, with) для каждого build-шага images-build."""
    out = []
    for step in _ci()["jobs"]["images-build"]["steps"]:
        w = step.get("with")
        if not isinstance(w, dict) or "file" not in w:
            continue
        m = _CI_TAG_RE.match(str(w["tags"]).strip())
        assert m, f"images-build публикует не ровно один тег ci-<sha>: {w['tags']!r}"
        out.append((Path(w["file"]), m.group("name"), w))
    return out


def _expected_image(site: str, dockerfile: Path) -> str:
    names = [name for df, name, _ in _published() if df == dockerfile]
    if len(names) > 1:  # фронт: по образу на площадку
        names = [n for n in names if n.endswith(f"-{site}")]
    assert len(names) == 1, f"{dockerfile}: images-build публикует {names or 'ничего'}"
    return names[0]


@pytest.mark.parametrize("site", sorted(SITES))
def test_registry_overlay_replaces_every_host_build(site: str):
    overlay = _services(f"docker-compose.registry.{site}.yml")
    problems = []
    for svc, dockerfile in sorted(_site_builds(site).items()):
        spec = overlay.get(svc)
        if spec is None:
            problems.append(f"{svc}: собирается на хосте, в registry-overlay'е нет")
            continue
        if spec.get("build", None) is not _RESET:
            problems.append(f"{svc}: нет `build: !reset null` — `compose build` собрал бы на хосте")
        m = _IMAGE_RE.match(str(spec.get("image", "")))
        if not m:
            problems.append(f"{svc}: image не {REGISTRY}/<образ>:sha-${{UK_IMAGE_SHA:?…}}")
            continue
        want = _expected_image(site, dockerfile)
        if m.group("name") != want:
            problems.append(f"{svc}: образ {m.group('name')}, а CI собирает {dockerfile} как {want}")
    assert not problems, f"docker-compose.registry.{site}.yml:\n" + "\n".join(problems)


@pytest.mark.parametrize("site", sorted(SITES))
def test_registry_overlay_adds_no_phantom_services(site: str):
    extra = set(_services(f"docker-compose.registry.{site}.yml")) - _site_service_names(site)
    assert not extra, f"сервисы вне набора {site} (compose создал бы их из image:): {sorted(extra)}"


def test_promote_covers_exactly_published_images():
    promote = _ci()["jobs"]["images-promote"]
    listed = set(promote["env"]["IMAGES"].split())
    published = {name for _, name, _ in _published()}
    assert listed == published, f"images-promote IMAGES ≠ images-build: {sorted(listed ^ published)}"
    used = {
        _IMAGE_RE.match(spec["image"]).group("name")
        for site in SITES
        for spec in _services(f"docker-compose.registry.{site}.yml").values()
    }
    assert used <= listed, f"overlay ссылается на непромоутимые образы: {sorted(used - listed)}"
    tag_deploy = (ROOT / "scripts" / "tag-deploy.sh").read_text(encoding="utf-8")
    m = re.search(r'^UK_IMAGES_DEFAULT="([^"]+)"', tag_deploy, re.M)
    assert m and set(m.group(1).split()) == listed, (
        "scripts/tag-deploy.sh UK_IMAGES_DEFAULT ≠ images-promote IMAGES — digest'ы в теге раскатки неполные"
    )


def test_every_image_is_built_for_host_platform():
    """Оба прод-хоста x86_64 — платформа задана явно, а не дефолтом buildx раннера."""
    wrong = [name for _, name, w in _published() if w.get("platforms") != "linux/amd64"]
    assert not wrong, f"images-build без platforms: linux/amd64: {wrong}"


def test_promote_waits_for_every_other_job():
    jobs = _ci()["jobs"]
    promote = jobs["images-promote"]
    assert set(promote["needs"]) == set(jobs) - {"images-promote"}, (
        "images-promote.needs обязан перечислять ВСЕ job'ы ci.yml: "
        f"{sorted((set(jobs) - {'images-promote'}) ^ set(promote['needs']))}"
    )
    assert "refs/heads/main" in promote["if"] and "push" in promote["if"]


def _flags(site: str) -> dict[str, str]:
    lines = (FLAGS_DIR / f"{site}.args").read_text(encoding="utf-8").splitlines()
    pairs = [ln.split("=", 1) for ln in lines if ln.strip() and not ln.lstrip().startswith("#")]
    return {k: v for k, v in pairs}


@pytest.mark.parametrize("site", sorted(SITES))
def test_frontend_flags_match_dockerfile_args(site: str):
    args = set(re.findall(r"^ARG (VITE_[A-Z0-9_]+)", FRONTEND_DOCKERFILE.read_text(), re.M))
    flags = _flags(site)
    assert set(flags) == args, f"{site}.args ≠ ARG VITE_* frontend/Dockerfile: {sorted(set(flags) ^ args)}"
    assert flags["VITE_BRAND"] == site
    step = next(w for _, name, w in _published() if name == f"uk-frontend-{site}")
    assert step["build-args"] == f"${{{{ steps.fe-args.outputs.{site} }}}}"
