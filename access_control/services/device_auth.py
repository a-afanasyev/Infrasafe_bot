"""Device authentication для edge ↔ backend (§9.1, решение CTO #8).

Пилотный профиль device-auth (mTLS — этап после пилота, §9.1):

* идентификация контроллера по заголовку ``X-AC-Controller`` (= ``controller_uid``)
  + предъявленный API-ключ ``X-AC-Key``; сверка ``sha256(key) == api_key_hash``;
* HMAC-SHA256 подпись тела на ПЕР-УСТРОЙСТВЕННОМ секрете (общий ключ запрещён §9.1).
  Канонический стринг: ``method \n path \n timestamp \n nonce \n sha256_hex(body)``;
* свежесть ``timestamp`` (окно конфигурируемо, дефолт 300 c);
* anti-replay по ``nonce`` через подключаемый ``NonceStore`` (in-memory дефолт +
  Redis-имплементация) с TTL; повтор nonce → 401;
* IP/VPN allowlist из ``edge_controllers.ip_allowlist`` (если задан — чужой IP → 403);
* контроллер обязан быть ``is_active`` И ``status='active'``.

Секрет НЕ выводится в логи (§11). Резолвится детерминированно через
``hmac_secret_ref`` (env-override или сид) — пилот синтетический.
"""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import logging
import os
import time
import uuid
from dataclasses import dataclass
from typing import Protocol

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from access_control.domain.enums import EdgeControllerStatus
from access_control.domain.equipment import EdgeController
from uk_management_bot.database.session import get_db

logger = logging.getLogger(__name__)

# Заголовки device-auth (пилот). Имена фиксированы — клиент и backend обязаны
# совпадать (edge-симулятор/conftest используют те же).
HEADER_CONTROLLER = "x-ac-controller"
HEADER_KEY = "x-ac-key"
HEADER_TIMESTAMP = "x-ac-timestamp"
HEADER_NONCE = "x-ac-nonce"
HEADER_SIGNATURE = "x-ac-signature"

# Окно свежести timestamp (§9.1), c. Конфигурируемо.
DEFAULT_TIMESTAMP_WINDOW_SECONDS = int(
    os.getenv("ACCESS_DEVICE_TS_WINDOW_SECONDS", "300")
)
# TTL nonce в anti-replay store (≥ окна свежести, иначе повтор после TTL пройдёт).
DEFAULT_NONCE_TTL_SECONDS = int(
    os.getenv("ACCESS_DEVICE_NONCE_TTL_SECONDS", "600")
)

# Имя env общего сида для детерминированного резолва пер-устройственного секрета.
# Хардкод-дефолта в коде нет (H2/M1): отсутствие env (и per-device override) →
# RuntimeError при резолве секрета. Тесты задают синтетический сид через окружение
# (access_control/tests/conftest.py). В проде — секрет-хранилище / per-device override.
_HMAC_SEED_ENV = "ACCESS_DEVICE_HMAC_SEED"


def _hmac_seed() -> str:
    seed = os.getenv(_HMAC_SEED_ENV)
    if not seed:
        raise RuntimeError(
            f"{_HMAC_SEED_ENV} (или per-device ACCESS_DEVICE_SECRET__<ref>) не задан: "
            "общий дефолтный HMAC-сид в коде запрещён (§9.1, §11)."
        )
    return seed


# --------------------------- крипто-примитивы ---------------------------


def hash_api_key(api_key: str) -> str:
    """Хэш API-ключа для хранения в ``edge_controllers.api_key_hash`` (§9.1)."""
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


def resolve_device_secret(secret_ref: str) -> bytes:
    """Резолвить пер-устройственный HMAC-секрет по ``hmac_secret_ref`` (решение CTO #8).

    Приоритет: env ``ACCESS_DEVICE_SECRET__<ref>`` (прод/стенд) → детерминированный
    дериват из сида (пилот). Общий ключ запрещён: секрет зависит от ``secret_ref``,
    т.е. различен на каждое устройство. Секрет НЕ логируется (§11).
    """
    override = os.getenv(f"ACCESS_DEVICE_SECRET__{secret_ref}")
    if override:
        return override.encode("utf-8")
    return hashlib.sha256(f"{_hmac_seed()}:{secret_ref}".encode("utf-8")).digest()


def body_hash(body: bytes) -> str:
    """sha256-хэш тела запроса (hex) — часть канонического стринга (§9.1)."""
    return hashlib.sha256(body or b"").hexdigest()


def canonical_string(
    method: str, path: str, timestamp: str | int, nonce: str, body: bytes
) -> str:
    """Канонический стринг подписи: method\\npath\\ntimestamp\\nnonce\\nsha256(body).

    TODO(accepted-risk L4, post-pilot): ``content-type`` не входит в канонический
    стринг — теоретически тело можно переинтерпретировать сменой content-type без
    инвалидизации подписи. Принятый риск пилота (endpoint'ы ждут JSON); после пилота
    включить content-type в подпись.
    """
    return "\n".join(
        [method.upper(), path, str(timestamp), nonce, body_hash(body)]
    )


def compute_signature(secret: bytes, canonical: str) -> str:
    """HMAC-SHA256 канонического стринга на пер-устройственном секрете (§9.1)."""
    return hmac.new(secret, canonical.encode("utf-8"), hashlib.sha256).hexdigest()


def sign_request(
    method: str,
    path: str,
    body: bytes,
    *,
    controller_uid: str,
    api_key: str,
    secret: bytes,
    timestamp: int | None = None,
    nonce: str | None = None,
) -> dict[str, str]:
    """Построить заголовки device-auth для запроса (edge-симулятор/conftest/прод-edge).

    ``timestamp``/``nonce`` можно зафиксировать (для тестов replay/freshness); по
    умолчанию — текущее время и случайный nonce.
    """
    ts = int(time.time()) if timestamp is None else int(timestamp)
    nc = nonce or uuid.uuid4().hex
    sig = compute_signature(secret, canonical_string(method, path, ts, nc, body))
    return {
        HEADER_CONTROLLER: controller_uid,
        HEADER_KEY: api_key,
        HEADER_TIMESTAMP: str(ts),
        HEADER_NONCE: nc,
        HEADER_SIGNATURE: sig,
    }


# ------------------------------ nonce store ------------------------------


class NonceStore(Protocol):
    """Anti-replay хранилище nonce (§9.1). ``seen`` атомарно проверяет-и-ставит."""

    def seen(self, key: str, ttl_seconds: int) -> bool:  # pragma: no cover - Protocol
        """True если nonce уже виден (replay); иначе сохраняет и возвращает False."""
        ...


class InMemoryNonceStore:
    """In-memory anti-replay (дефолт): процесс-локальный, с TTL-протуханием.

    Для одного процесса backend пилота достаточно. Прод/несколько воркеров —
    ``RedisNonceStore`` (общий store), иначе replay пройдёт на другом воркере.
    """

    def __init__(self) -> None:
        self._seen: dict[str, float] = {}

    def seen(self, key: str, ttl_seconds: int) -> bool:
        now = time.monotonic()
        # Лёгкая чистка протухших, чтобы словарь не рос неограниченно.
        if len(self._seen) > 4096:
            self._seen = {k: v for k, v in self._seen.items() if v > now}
        exp = self._seen.get(key)
        if exp is not None and exp > now:
            return True
        self._seen[key] = now + ttl_seconds
        return False


class RedisNonceStore:
    """Anti-replay на Redis (прод/несколько воркеров): атомарный ``SET NX EX`` (§9.1)."""

    def __init__(self, client) -> None:
        self._client = client

    def seen(self, key: str, ttl_seconds: int) -> bool:
        # SET key 1 NX EX ttl → True если выставлено (новый nonce), None если уже был.
        was_set = self._client.set(name=f"ac:nonce:{key}", value="1", nx=True, ex=ttl_seconds)
        return not bool(was_set)


_default_store: NonceStore | None = None


def get_nonce_store() -> NonceStore:
    """Синглтон nonce-store. Backend выбирается env ``ACCESS_NONCE_BACKEND``.

    Явный env — высший приоритет: ``redis`` → ``RedisNonceStore`` из
    ``settings.REDIS_URL`` (синхронный клиент, проверяется ``ping``); ``memory`` →
    ``InMemoryNonceStore``. При ОТСУТСТВИИ переменной дефолт зависит от
    ``settings.DEBUG`` (SEC-02/аудит #4, fail-closed): в проде (``DEBUG=false``) —
    ``redis``, в dev/тестах — ``memory``. Раньше дефолт был безусловно ``memory``:
    на multi-worker проде anti-replay становился process-local и replay проходил
    на другом воркере. При ``redis`` и недоступном Redis — FATAL (RuntimeError),
    БЕЗ тихого отката на in-memory (M2).
    """
    global _default_store
    if _default_store is not None:
        return _default_store
    backend = os.getenv("ACCESS_NONCE_BACKEND")
    if backend is None:
        from uk_management_bot.config.settings import settings
        backend = "memory" if settings.DEBUG else "redis"
    backend = backend.lower()
    if backend == "redis":
        try:
            import redis  # type: ignore

            from uk_management_bot.config.settings import settings

            client = redis.Redis.from_url(settings.REDIS_URL)
            client.ping()  # fail-fast: убедиться, что Redis действительно доступен
            _default_store = RedisNonceStore(client)
        except Exception as exc:  # noqa: BLE001
            # Логируем предупреждение, но НЕ откатываемся тихо — это FATAL (M2).
            logger.warning(
                "redis nonce-store недоступен (%s) — FATAL, тихий откат на in-memory "
                "запрещён (anti-replay не должен молча деградировать)", exc
            )
            raise RuntimeError(
                "ACCESS_NONCE_BACKEND=redis, но Redis-anti-replay недоступен; "
                "тихий откат на in-memory запрещён (M2, §9.1)."
            ) from exc
    else:
        _default_store = InMemoryNonceStore()
    return _default_store


def reset_nonce_store(store: NonceStore | None = None) -> None:
    """Сбросить/подменить синглтон nonce-store (для тестов изоляции)."""
    global _default_store
    _default_store = store


# ------------------------------ verification -----------------------------


@dataclass(frozen=True)
class DeviceAuthError(Exception):
    """Ошибка device-auth с HTTP-кодом (401 — credential, 403 — IP allowlist)."""

    status_code: int
    detail: str


# Обобщённый ответ на любую ошибку аутентификации credential (M4): клиенту не
# раскрываем «unknown controller» vs «invalid api key» vs «replay» — иначе это
# enumeration-канал. Конкретика — только в server-side лог (без секретов/ключей/ПД).
GENERIC_AUTH_DETAIL = "unauthorized"


def _unauthorized(log_reason: str, *, controller_uid: str | None = None) -> DeviceAuthError:
    """Залогировать конкретную причину (server-side) и вернуть обобщённый 401 (M4)."""
    logger.warning("device-auth rejected: %s controller=%s", log_reason, controller_uid)
    return DeviceAuthError(401, GENERIC_AUTH_DETAIL)


def _trusted_proxies() -> set[str]:
    """Множество доверенных прокси из env ``ACCESS_TRUSTED_PROXIES`` (M5). Пусто — нет прокси."""
    raw = os.getenv("ACCESS_TRUSTED_PROXIES", "")
    return {x.strip() for x in raw.split(",") if x.strip()}


def resolve_client_ip(request: "Request") -> str | None:
    """Определить реальный IP клиента с учётом доверенного прокси (M5, §9.1).

    Если непосредственный ``request.client.host`` входит в ``ACCESS_TRUSTED_PROXIES``,
    реальный IP берётся из первого ``X-Forwarded-For`` (или ``X-Real-IP``) — иначе за
    прокси allowlist всегда видел бы IP прокси и не работал. Без доверенных прокси
    (дефолт) — поведение как раньше: прямой ``client.host`` (XFF подделываем,
    поэтому НЕ доверяем заголовкам от непроверенного источника).
    """
    direct = request.client.host if request.client else None
    if direct is not None and direct in _trusted_proxies():
        xff = request.headers.get("x-forwarded-for")
        if xff:
            return xff.split(",")[0].strip()
        xri = request.headers.get("x-real-ip")
        if xri:
            return xri.strip()
    return direct


def _ip_entry_matches(client_ip: str | None, entry: str) -> bool:
    """Совпадение IP клиента с записью allowlist: точный IP ИЛИ CIDR-подсеть (§9.1).

    Порт из B (``security/device_auth.py``): запись может быть как одиночным IP
    (``10.0.0.5``), так и подсетью (``10.0.0.0/24``). Невалидные записи/IP молча
    игнорируются (не матчат) — fail-safe.
    """
    if client_ip is None:
        return False
    if client_ip == entry:
        return True
    try:
        return ipaddress.ip_address(client_ip) in ipaddress.ip_network(entry, strict=False)
    except ValueError:
        return False


def _client_ip_allowed(controller: EdgeController, client_ip: str | None) -> bool:
    """Разрешён ли IP клиента allowlist'ом контроллера (§9.1). Пустой список — без ограничения.

    Поддерживает как точные IP, так и CIDR-подсети в записях allowlist (порт из B).
    """
    allowlist = controller.ip_allowlist
    if not allowlist:
        return True
    if isinstance(allowlist, (list, tuple)):
        entries = [str(x).strip() for x in allowlist if str(x).strip()]
    else:
        # На случай нестандартного хранения — строка с запятыми.
        entries = [x.strip() for x in str(allowlist).split(",") if x.strip()]
    return any(_ip_entry_matches(client_ip, entry) for entry in entries)


def authenticate(
    db: Session,
    *,
    method: str,
    path: str,
    body: bytes,
    headers: "object",
    client_ip: str | None,
    nonce_store: NonceStore | None = None,
    timestamp_window_seconds: int = DEFAULT_TIMESTAMP_WINDOW_SECONDS,
    nonce_ttl_seconds: int = DEFAULT_NONCE_TTL_SECONDS,
) -> EdgeController:
    """Аутентифицировать edge-запрос (§9.1). Возвращает контроллер или ``DeviceAuthError``.

    Порядок проверок: наличие заголовков → контроллер (active) → IP allowlist →
    API-ключ → свежесть timestamp → HMAC-подпись → anti-replay nonce. Nonce
    «погашается» ПОСЛЕДНИМ, после верной подписи — иначе невалидный запрос съедал бы
    nonce. PD-safe логирование (без секрета/ключа/номера, §11).
    """
    store = nonce_store or get_nonce_store()

    def _h(name: str) -> str | None:
        # Starlette Headers — регистронезависимый доступ.
        try:
            return headers.get(name)
        except Exception:  # noqa: BLE001
            return None

    controller_uid = _h(HEADER_CONTROLLER)
    api_key = _h(HEADER_KEY)
    timestamp_raw = _h(HEADER_TIMESTAMP)
    nonce = _h(HEADER_NONCE)
    signature = _h(HEADER_SIGNATURE)

    if not all([controller_uid, api_key, timestamp_raw, nonce, signature]):
        raise DeviceAuthError(401, "missing device credentials")

    controller = (
        db.query(EdgeController)
        .filter(
            EdgeController.controller_uid == controller_uid,
            EdgeController.is_active.is_(True),
            EdgeController.status == EdgeControllerStatus.ACTIVE.value,
        )
        .first()
    )
    if controller is None:
        raise _unauthorized("unknown or inactive controller", controller_uid=controller_uid)

    # IP/VPN allowlist (§9.1): отдельный 403 — credential валиден, но источник чужой.
    if not _client_ip_allowed(controller, client_ip):
        logger.warning(
            "device-auth ip rejected: controller=%s ip=%s", controller_uid, client_ip
        )
        raise DeviceAuthError(403, "client ip not allowed")

    # API-ключ: сверка хэша (§9.1). Постоянное сравнение хэшей.
    if not hmac.compare_digest(hash_api_key(api_key), controller.api_key_hash or ""):
        raise _unauthorized("invalid api key", controller_uid=controller_uid)

    # Свежесть timestamp (§9.1).
    try:
        ts = int(timestamp_raw)
    except (TypeError, ValueError):
        raise _unauthorized("invalid timestamp", controller_uid=controller_uid)
    if abs(int(time.time()) - ts) > timestamp_window_seconds:
        raise _unauthorized("stale timestamp", controller_uid=controller_uid)

    # HMAC-подпись тела на пер-устройственном секрете (§9.1). Колонки hmac_secret_ref
    # в пилотной модели нет (решение CTO #8 — синтетический секрет): ref =
    # controller_uid (уникален → секрет пер-устройственный, общий ключ запрещён §9.1).
    secret_ref = getattr(controller, "hmac_secret_ref", None) or controller.controller_uid
    secret = resolve_device_secret(secret_ref)
    expected = compute_signature(
        secret, canonical_string(method, path, ts, nonce, body)
    )
    if not hmac.compare_digest(expected, signature):
        raise _unauthorized("invalid signature", controller_uid=controller_uid)

    # Anti-replay nonce (§9.1) — последним, чтобы невалидный запрос не гасил nonce.
    if store.seen(f"{controller_uid}:{nonce}", nonce_ttl_seconds):
        raise _unauthorized("nonce replay detected", controller_uid=controller_uid)

    return controller


async def authenticate_edge(
    request: Request, db: Session = Depends(get_db)
) -> EdgeController:
    """FastAPI-зависимость device-auth для ВСЕХ edge-endpoint'ов (§9.1).

    Аутентифицирует по заголовкам + подписи тела. Для path-scoped endpoint'ов
    (``/edge/{controller_id}/...``) дополнительно требует, чтобы ``controller_id``
    в пути совпадал с аутентифицированным контроллером (чужой путь → 403, §9.1:
    «клиент не может запросить кэш/команды другой зоны»).
    """
    body = await request.body()
    # M5: за доверенным прокси берём реальный IP из X-Forwarded-For (иначе allowlist
    # видит только IP прокси). Без доверенных прокси — прямой client.host.
    client_ip = resolve_client_ip(request)
    try:
        controller = authenticate(
            db,
            method=request.method,
            path=request.url.path,
            body=body,
            headers=request.headers,
            client_ip=client_ip,
        )
    except DeviceAuthError as err:
        raise HTTPException(status_code=err.status_code, detail=err.detail)

    path_uid = request.path_params.get("controller_id")
    if path_uid is not None and path_uid != controller.controller_uid:
        # Контроллер не может действовать на пути чужого controller_id (§9.1).
        raise HTTPException(status_code=403, detail="controller path mismatch")
    return controller
