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
    "docker-compose.infrasafe.yml",
)
APP_SERVICES = {
    "app", "group-intake-bot", "api", "access-api", "frontend",
    "media-service", "resource-api", "resource-worker", "payment-api",
}


class _ComposeLoader(yaml.SafeLoader):
    """SafeLoader, понимающий compose-теги `!override`/`!reset` как обычные узлы."""


class _Override(list):
    """Список под `!override` — заменяет, а не дополняет значение базового файла."""


def _construct_tagged(loader: yaml.SafeLoader, tag_suffix: str, node: yaml.Node):
    if isinstance(node, yaml.MappingNode):
        return loader.construct_mapping(node)
    if isinstance(node, yaml.SequenceNode):
        items = loader.construct_sequence(node)
        return _Override(items) if tag_suffix == "override" else items
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


# Python-сервисы работают не от root и не трогают привилегии в entrypoint — им не
# нужна ни одна capability. Фронт (nginx) не входит: ему нужны CHOWN/SETUID/SETGID.
PYTHON_SERVICES = APP_SERVICES - {"frontend"}


def test_python_services_drop_all_capabilities():
    """A10-INF-03 (сужен 2026-11-05): cap_drop: [ALL]; read_only/pids_limit — нет."""
    seen: dict[str, list[str]] = {}
    for name in COMPOSE_FILES:
        for svc, body in _services(name).items():
            if svc in PYTHON_SERVICES and body:
                seen.setdefault(svc, []).extend(body.get("cap_drop") or [])
    missing = sorted(svc for svc in PYTHON_SERVICES if "ALL" not in seen.get(svc, []))
    assert missing == [], missing


def test_payment_services_never_join_shared_network():
    """A10-INT-04: на profk `uk-network` — общая с InfraSafe (edge-nginx, asset-web);
    платёжная БД и payment-api живут только в приватной `uk-internal`."""
    offenders = []
    for svc, body in _services("docker-compose.payments.yml").items():
        nets = (body or {}).get("networks") or []
        names = list(nets) if isinstance(nets, (list, dict)) else [nets]
        if svc.startswith("payment") and "uk-network" in names:
            offenders.append(svc)
    assert offenders == [], offenders


def test_env_example_does_not_carry_superuser_credentials():
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    offenders = re.findall(r"^(POSTGRES_PASSWORD|DATABASE_URL)=", text, re.M)
    assert offenders == [], offenders


def test_postgres_healthchecks_name_database():
    """A11 HOST-11-11: pg_isready без -d стучится в БД с именем пользователя —
    на resource-postgres это 25 тыс. «FATAL: database "resource" does not exist»
    за трое суток, в которых тонут настоящие ошибки аутентификации."""
    offenders = []
    for name in COMPOSE_FILES:
        for svc, cfg in (_services(name) or {}).items():
            test = (cfg or {}).get("healthcheck", {}).get("test") or []
            cmd = " ".join(test) if isinstance(test, list) else str(test)
            if "pg_isready" in cmd and " -d " not in cmd:
                offenders.append(f"{name}:{svc}")
    assert offenders == []


SITE_NETWORK_OVERLAYS = ("docker-compose.profk.yml", "docker-compose.infrasafe.yml")
DATABASES = ("postgres", "redis", "resource-postgres")


def test_databases_never_share_edge_network():
    """A11 HOST-11-05 / A10-HOST-07: в `uk-network` сидит edge-nginx InfraSafe —
    БД на обеих площадках только в приватной `uk-internal`. Именно `!override`:
    без него список сливается с базовым и `uk-network` возвращается."""
    offenders = []
    for name in SITE_NETWORK_OVERLAYS:
        services = _services(name)
        for db in DATABASES:
            nets = (services.get(db) or {}).get("networks")
            if not isinstance(nets, _Override) or list(nets) != ["uk-internal"]:
                offenders.append(f"{name}:{db}")
    assert offenders == [], offenders
