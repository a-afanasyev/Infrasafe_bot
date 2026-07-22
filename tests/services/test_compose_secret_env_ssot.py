"""ARCH-106 SSOT-гейт: секреты должны быть проброшены в compose явным `environment:`-маппингом.

После Doppler-cutover (Phase 1/2) секреты приходят из Doppler в окружение compose-процесса,
а контейнер получает ТОЛЬКО перечисленные в `environment:` имена — `env_file(.env)` на проде
от секретов очищен. Значит новый секрет, добавленный в settings без строки в compose, молча
приедет пустым. Этот гейт ловит такую регрессию.

Контракт по модификаторам:
  * маппинг «переменная целиком» (`- VAR=${VAR}`) обязан иметь `:?` (обязательный) или
    `:-` (опциональный) — голая подстановка означала бы тихое пустое значение;
  * имя, встроенное ВНУТРЬ составной строки (URI), намеренно идёт без модификатора —
    см. _URI_EMBEDDED ниже, для них проверяется только присутствие.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

BASE = ROOT / "docker-compose.yml"
PROFK = ROOT / "docker-compose.profk.yml"
MEDIA = ROOT / "docker-compose.media.yml"

# Секрет -> сервисы, которым он обязан быть проброшен, в базовом и profk-файлах.
# app/api/access-api/migrate импортируют общий settings.py — его эагерная prod-валидация
# требует всё это во всех четырёх (ARCH-106 план, «Ключевая находка»).
# OUTBOX_SOURCE_INSTANCE (ARCH-010) — не секрет, но так же обязателен eager-валидацией.
CORE_REQUIRED = (
    "BOT_TOKEN", "ADMIN_PASSWORD", "JWT_SECRET", "INVITE_SECRET",
    "OUTBOX_SOURCE_INSTANCE",
)

EXPECTED = {
    "app": CORE_REQUIRED,
    "api": CORE_REQUIRED + (
        "HEALTH_METRICS_TOKEN",
        "INFRASAFE_INVENTORY_TOKEN",
        "UK_WEBHOOK_SECRET",
        "MEDIA_SERVICE_API_KEY",
        "MEDIA_API_KEY",
        # Phase 2: dual-secret ротация — подписант и верификатор оба в api.
        "INFRASAFE_WEBHOOK_SECRET_NEXT",
        "UK_WEBHOOK_SECRET_NEXT",
    ),
    "access-api": CORE_REQUIRED + (
        "ACCESS_CODE_SECRET",
        "ACCESS_DEVICE_HMAC_SEED",
        "ACCESS_PHOTO_URL_SECRET",
        "ACCESS_SNAPSHOT_SIGNING_SEED",
        "MEDIA_API_KEY",
    ),
    "migrate": CORE_REQUIRED,
    "resource-api": ("RESOURCE_SESSION_SECRET", "RESOURCE_SERVICE_TOKEN"),
    "resource-worker": ("RESOURCE_SESSION_SECRET", "RESOURCE_SERVICE_TOKEN"),
}

# Phase 2: media-service объявлен в profk-файле и в media-overlay — набор одинаковый.
MEDIA_EXPECTED = (
    "MEDIA_BOT_TOKEN",
    "MEDIA_SECRET_KEY",
    "MEDIA_API_KEYS",
    "MEDIA_DATABASE_URL",
)

# Имена, встроенные внутрь составных строк (URI). Модификатора у них нет намеренно:
#   * RESOURCE_POSTGRES_PASSWORD прикрыт `:?` того же имени у resource-postgres —
#     интерполяция падает на уровне всего файла;
#   * REDIS_PASSWORD не прикрыт ничем (он опционален: `${REDIS_PASSWORD:+--requirepass ...}`),
#     пустое значение даёт беспарольный redis — известный пробел fail-fast, отдельный
#     follow-up вне ARCH-106 Phase 2.
_URI_EMBEDDED = {"REDIS_PASSWORD", "RESOURCE_POSTGRES_PASSWORD"}

_SERVICE_RE = re.compile(r"^  ([a-z0-9][a-z0-9_-]*):\s*$")


def _service_blocks(path: Path) -> dict[str, list[str]]:
    """Строки каждого сервиса верхнего уровня (грубый разбор — без зависимости от pyyaml)."""
    blocks: dict[str, list[str]] = {}
    current = None
    for line in path.read_text(encoding="utf-8").splitlines():
        match = _SERVICE_RE.match(line)
        if match:
            current = match.group(1)
            blocks[current] = []
        elif current is not None:
            if line and not line.startswith(" "):
                current = None
            else:
                blocks[current].append(line)
    return blocks


def _mapping_for(lines: list[str], var: str) -> str | None:
    """Строка `environment:`-маппинга, подставляющая ${var}, или None."""
    pattern = re.compile(r"\$\{" + re.escape(var) + r"[:}]")
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#") or not stripped.startswith("- "):
            continue
        if pattern.search(stripped):
            return stripped
    return None


def _check(path: Path, service: str, variables: tuple[str, ...]) -> list[str]:
    blocks = _service_blocks(path)
    assert service in blocks, f"{path.name}: сервис {service} не найден"
    problems = []
    for var in variables:
        mapping = _mapping_for(blocks[service], var)
        if mapping is None:
            problems.append(f"{path.name}:{service}: нет environment-маппинга для {var}")
            continue
        if var in _URI_EMBEDDED:
            continue
        if not re.search(r"\$\{" + re.escape(var) + r"(:\?|:-)", mapping):
            problems.append(
                f"{path.name}:{service}: {var} без :?/:- — тихая пустая подстановка ({mapping})"
            )
    return problems


def test_core_secrets_mapped_in_both_compose_files():
    problems = []
    for path in (BASE, PROFK):
        for service, variables in EXPECTED.items():
            problems += _check(path, service, variables)
    assert not problems, "ARCH-106 SSOT: " + "; ".join(problems)


def test_media_secrets_mapped_in_both_declarations():
    problems = []
    for path in (PROFK, MEDIA):
        problems += _check(path, "media-service", MEDIA_EXPECTED)
    assert not problems, "ARCH-106 Phase 2 SSOT: " + "; ".join(problems)


def test_redis_url_built_from_password_not_taken_whole():
    """REDIS_URL собирается из REDIS_PASSWORD — целиком из .env он Doppler-cutover обходил бы."""
    offenders = []
    for path in (BASE, PROFK):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if re.search(r"REDIS_URL=\$\{REDIS_URL", stripped):
                offenders.append(f"{path.name}:{lineno}: {stripped}")
    assert not offenders, (
        "REDIS_URL берётся из .env целиком — пароль перестаёт приходить из Doppler: "
        + "; ".join(offenders)
    )
