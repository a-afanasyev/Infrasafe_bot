"""A10-INF-03/INF-04/HOST-01: гейты compose и `.env.example` по аудиту 2026-10-23.

* ротация json-file логов объявлена у каждого сервиса (на 105 нет daemon.json);
* прикладные сервисы без privilege escalation;
* `.env.example` не предлагает класть суперюзер-пароль/DATABASE_URL в общий
  `.env` — именно так он попал в окружение app/api/access-api на обоих продах.
"""
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILES = (
    "docker-compose.yml",
    "docker-compose.profk.yml",
    "docker-compose.media.yml",
    "docker-compose.payments.yml",
)
APP_SERVICES = {
    "app", "group-intake-bot", "api", "access-api", "frontend",
    "media-service", "resource-api", "resource-worker", "payment-api",
}


class _ComposeLoader(yaml.SafeLoader):
    """SafeLoader, понимающий compose-теги `!override`/`!reset` как обычные узлы."""


def _construct_tagged(loader: yaml.SafeLoader, tag_suffix: str, node: yaml.Node):
    if isinstance(node, yaml.MappingNode):
        return loader.construct_mapping(node)
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node)
    return loader.construct_scalar(node)


_ComposeLoader.add_multi_constructor("!", _construct_tagged)


def _services(name: str) -> dict:
    return yaml.load((ROOT / name).read_text(encoding="utf-8"), Loader=_ComposeLoader)["services"]


def test_every_service_declares_log_rotation():
    missing = [
        f"{name}:{svc}"
        for name in COMPOSE_FILES
        for svc, body in _services(name).items()
        if body is not None and not (body.get("logging") or {}).get("options", {}).get("max-size")
        # overlay-фрагменты без собственного logging наследуют его из базового файла
        and name == "docker-compose.yml"
    ]
    assert missing == [], missing


def test_app_services_forbid_privilege_escalation():
    seen: dict[str, list[str]] = {}
    for name in COMPOSE_FILES:
        for svc, body in _services(name).items():
            if svc in APP_SERVICES and body:
                seen.setdefault(svc, []).extend(body.get("security_opt") or [])
    missing = [svc for svc in APP_SERVICES if "no-new-privileges:true" not in seen.get(svc, [])]
    assert missing == [], missing


def test_env_example_does_not_carry_superuser_credentials():
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    offenders = re.findall(r"^(POSTGRES_PASSWORD|DATABASE_URL)=", text, re.M)
    assert offenders == [], offenders
