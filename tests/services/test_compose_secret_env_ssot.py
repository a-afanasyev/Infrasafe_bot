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

AUD6-P2-38: docker-compose.profk.yml — больше НЕ standalone, а тонкий override поверх
docker-compose.yml (`-f docker-compose.yml -f docker-compose.profk.yml`). Значит profk-блок
сервиса сам по себе env-маппинги секретов не несёт — эффективное окружение сервиса на
profk = base-блок + override-блок (compose сливает `environment:` по-переменно, override
приоритетнее). Гейт проверяет profk именно по этой ОБЪЕДИНЁННОЙ картине: строки
override-блока идут ПЕРВЫМИ (зеркалит приоритет мержа), base-блок — фолбэк. Так гейт
остаётся содержательным: секрет, пропавший из base и не добавленный в override, ловится;
плохой (без :?/:-) override-маппинг поверх хорошего base-маппинга — тоже.
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
    # Group Intake — выделенный бот (свой polling-процесс за compose-профилем).
    # Секреты фичи опциональны на уровне compose (:-) — «флаг включён без
    # токена/ключа» ловит eager-валидация settings.py; сам сервис без флага
    # сознательно не стартует.
    "group-intake-bot": CORE_REQUIRED + (
        "GROUP_INTAKE_BOT_TOKEN",
        "ANTHROPIC_API_KEY",
        "MEDIA_API_KEY",
    ),
    "api": CORE_REQUIRED + (
        "HEALTH_METRICS_TOKEN",
        "INFRASAFE_INVENTORY_TOKEN",
        "UK_WEBHOOK_SECRET",
        "MEDIA_SERVICE_API_KEY",
        "MEDIA_API_KEY",
        # Phase 2: dual-secret ротация — подписант и верификатор оба в api.
        "INFRASAFE_WEBHOOK_SECRET_NEXT",
        "UK_WEBHOOK_SECRET_NEXT",
        # ARCH-107: dual-key ротация JWT — подписант токенов в api.
        "JWT_SECRET_NEXT",
    ),
    "access-api": CORE_REQUIRED + (
        "ACCESS_CODE_SECRET",
        "ACCESS_DEVICE_HMAC_SEED",
        "ACCESS_PHOTO_URL_SECRET",
        "ACCESS_SNAPSHOT_SIGNING_SEED",
        "MEDIA_API_KEY",
        # ARCH-107: верификатор JWT в access-api обязан знать оба ключа окна.
        "JWT_SECRET_NEXT",
    ),
    "migrate": CORE_REQUIRED,
    # AUD6-P1-2: runtime — под least-privilege ролью resource_app (пароль
    # встроен в RESOURCE_DATABASE_URL с инлайн-:?); владельческий пароль
    # остаётся только у one-shot'ов provision/migrate.
    "resource-api": (
        "RESOURCE_SESSION_SECRET", "RESOURCE_SERVICE_TOKEN", "RESOURCE_APP_PASSWORD",
    ),
    "resource-worker": (
        "RESOURCE_SESSION_SECRET", "RESOURCE_SERVICE_TOKEN", "RESOURCE_APP_PASSWORD",
    ),
    "resource-migrate": ("RESOURCE_POSTGRES_PASSWORD",),
    "resource-provision-roles": ("RESOURCE_POSTGRES_PASSWORD", "RESOURCE_APP_PASSWORD"),
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


def _check_blocks(
    blocks: dict[str, list[str]], label: str, service: str, variables: tuple[str, ...]
) -> list[str]:
    assert service in blocks, f"{label}: сервис {service} не найден"
    problems = []
    for var in variables:
        mapping = _mapping_for(blocks[service], var)
        if mapping is None:
            problems.append(f"{label}:{service}: нет environment-маппинга для {var}")
            continue
        if var in _URI_EMBEDDED:
            continue
        if not re.search(r"\$\{" + re.escape(var) + r"(:\?|:-)", mapping):
            problems.append(
                f"{label}:{service}: {var} без :?/:- — тихая пустая подстановка ({mapping})"
            )
    return problems


def _check(path: Path, service: str, variables: tuple[str, ...]) -> list[str]:
    return _check_blocks(_service_blocks(path), path.name, service, variables)


def _profk_effective_blocks() -> dict[str, list[str]]:
    """Эффективная картина profk-деплоя: base-блок + override-блок (AUD6-P2-38).

    Строки override-блока идут ПЕРВЫМИ: `_mapping_for` возвращает первое совпадение,
    что зеркалит per-key приоритет `environment:`-мержа compose — override-маппинг
    переменной побеждает base-маппинг, поэтому и валидироваться должен именно он.
    Сервисы, объявленные только в override (media-service/media-migrate), приходят
    целиком из profk-файла.
    """
    base = _service_blocks(BASE)
    profk = _service_blocks(PROFK)
    combined = dict(base)
    for name, lines in profk.items():
        combined[name] = lines + base.get(name, [])
    return combined


def test_core_secrets_mapped_in_both_compose_files():
    problems = []
    for service, variables in EXPECTED.items():
        problems += _check(BASE, service, variables)
        # profk — тонкий override: проверяем объединение base+override, а не файл сам по себе.
        problems += _check_blocks(
            _profk_effective_blocks(), "base+profk", service, variables
        )
    assert not problems, "ARCH-106 SSOT: " + "; ".join(problems)


def test_media_secrets_mapped_in_both_declarations():
    # media-service объявлен целиком в profk-override (на 105 — в media-overlay);
    # объединённая картина для него совпадает с profk-блоком, base его не содержит.
    problems = _check_blocks(
        _profk_effective_blocks(), "base+profk", "media-service", MEDIA_EXPECTED
    )
    problems += _check(MEDIA, "media-service", MEDIA_EXPECTED)
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
