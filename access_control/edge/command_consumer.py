"""Минимальный симулятор edge-консьюмера durable-канала (§9.2, критерии §15.5/§15.6).

Цикл стороны edge: pull(``/commands/next``) → ``relay.open()`` → ack(``/ack``) с
дедупом физических открытий по ``command_id``. Одна команда, пришедшая и fast-path
(синхронный ответ anpr), и durable pull, исполняет реле РОВНО один раз; повторная
обработка возвращает сохранённый результат.

Дедуп-хранилище (``ProcessedStore``) ПОДКЛЮЧАЕМО: дефолт — in-memory
(``InMemoryProcessedStore``), для продакшена есть простой персистентный
(``FileProcessedStore``), переживающий рестарт процесса edge. Прод-edge ОБЯЗАН
использовать персистентный store: с in-memory после рестарта дедуп теряется и реле
может открыться повторно.

Отправку ANPR-событий консьюмер НЕ делает — это Ф6. Здесь только приём/исполнение
команд через реальные HTTP-endpoints (клиент duck-typed: ``.get``/``.post``).
"""
from __future__ import annotations

import datetime as dt
import json
import os
import tempfile
from dataclasses import dataclass, replace
from typing import Any, Protocol

from access_control.integrations.relay import RelayAdapter, RelayCommand, RelayResult

_BASE = "/api/v1/access/edge"


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class ProcessedStore(Protocol):
    """Хранилище обработанных command_id (дедуп физических открытий реле, §9.2)."""

    def get(self, command_id: str) -> RelayResult | None:  # pragma: no cover
        ...

    def put(self, command_id: str, result: RelayResult) -> None:  # pragma: no cover
        ...


class InMemoryProcessedStore:
    """In-memory дедуп (дефолт). НЕ переживает рестарт — для тестов/одиночного процесса."""

    def __init__(self) -> None:
        self._results: dict[str, RelayResult] = {}

    def get(self, command_id: str) -> RelayResult | None:
        return self._results.get(command_id)

    def put(self, command_id: str, result: RelayResult) -> None:
        self._results[command_id] = result


class FileProcessedStore:
    """Персистентный дедуп на JSON-файле — переживает рестарт процесса edge (§9.2).

    Минимальная реализация без БД: ``command_id -> {opened, detail}``. Запись —
    атомарная (tmp + ``os.replace``). Для пилота (один процесс edge) достаточно;
    прод-edge обязан персистить именно так (или таблицей), иначе дедуп теряется.
    """

    def __init__(self, path: str) -> None:
        self._path = path
        self._data: dict[str, dict] = {}
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as fh:
                    self._data = json.load(fh)
            except (OSError, json.JSONDecodeError):
                self._data = {}

    def get(self, command_id: str) -> RelayResult | None:
        rec = self._data.get(command_id)
        if rec is None:
            return None
        return RelayResult(
            command_id=command_id,
            opened=bool(rec.get("opened", False)),
            deduplicated=False,
            detail=rec.get("detail"),
        )

    def put(self, command_id: str, result: RelayResult) -> None:
        self._data[command_id] = {"opened": result.opened, "detail": result.detail}
        self._flush()

    def _flush(self) -> None:
        directory = os.path.dirname(self._path) or "."
        fd, tmp = tempfile.mkstemp(dir=directory, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(self._data, fh)
            os.replace(tmp, self._path)
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise


@dataclass(frozen=True)
class ProcessOutcome:
    """Итог обработки одной команды edge'ом."""

    command_id: str
    relay_opened: bool
    relay_deduplicated: bool
    acked: bool
    ack_replayed: bool
    expired: bool = False


class EdgeCommandConsumer:
    """Edge-сторона: pull → relay.open → ack с дедупом реле по command_id.

    ``client`` — HTTP-клиент (TestClient/прод-edge http, duck-typed ``.get``/``.post``),
    ``controller_uid`` — идентичность устройства в пути, ``relay`` — адаптер реле,
    ``processed_store`` — дедуп обработанных command_id (дефолт in-memory).
    """

    def __init__(
        self,
        client: Any,
        controller_uid: str,
        relay: RelayAdapter,
        *,
        base: str = _BASE,
        processed_store: ProcessedStore | None = None,
    ) -> None:
        self._client = client
        self._uid = controller_uid
        self._relay = relay
        self._base = base
        # Дедуп физических открытий реле по command_id (§9.2, реле ≤1 раза).
        self._store: ProcessedStore = processed_store or InMemoryProcessedStore()

    def _open_once(self, command_id: str, barrier_id: int) -> RelayResult:
        """Открыть реле не более одного раза на command_id (дедуп через store)."""
        saved = self._store.get(command_id)
        if saved is not None:
            return replace(saved, deduplicated=True)
        result = self._relay.open(
            RelayCommand(command_id=command_id, barrier_id=barrier_id)
        )
        self._store.put(command_id, result)
        return result

    @staticmethod
    def _is_expired(expires_at_raw: str | None) -> bool:
        """Истекла ли команда по body.expires_at (защита от протухшей доставки, §9.2)."""
        if not expires_at_raw:
            return False
        try:
            expires_at = dt.datetime.fromisoformat(expires_at_raw)
        except ValueError:
            return False
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=dt.timezone.utc)
        return expires_at <= _utcnow()

    def on_fast_path(self, command_id: str, barrier_id: int) -> ProcessOutcome:
        """Команда доставлена fast-path (синхронный ответ anpr): открыть реле сразу.

        ACK не выполняется: команда ещё ``pending`` (без lease), подтверждение идёт
        через durable pull. Дедуп гарантирует, что pull той же команды не откроет
        реле повторно.
        """
        relay_result = self._open_once(command_id, barrier_id)
        return ProcessOutcome(
            command_id=command_id,
            relay_opened=relay_result.opened,
            relay_deduplicated=relay_result.deduplicated,
            acked=False,
            ack_replayed=False,
        )

    def pull_once(self) -> ProcessOutcome | None:
        """Один durable-цикл: lease → relay.open (дедуп) → ack. None если очередь пуста.

        Протухшую (``expires_at`` в прошлом) команду НЕ открываем: реле не трогаем,
        ack'аем как expired/skip, чтобы снять её с очереди (§9.2).
        """
        resp = self._client.get(f"{self._base}/{self._uid}/commands/next")
        if resp.status_code == 204:
            return None
        resp.raise_for_status()
        body = resp.json()
        command_id = body["command_id"]

        if self._is_expired(body.get("expires_at")):
            # Реле НЕ открываем; ack как expired/skip (снять с очереди).
            ack = self._client.post(
                f"{self._base}/{self._uid}/commands/{command_id}/ack",
                json={
                    "lease_token": body["lease_token"],
                    "result": {"skipped": "expired"},
                },
            )
            ack_body = ack.json() if ack.status_code == 200 else {}
            return ProcessOutcome(
                command_id=command_id,
                relay_opened=False,
                relay_deduplicated=False,
                acked=ack.status_code == 200,
                ack_replayed=bool(ack_body.get("replayed", False)),
                expired=True,
            )

        relay_result = self._open_once(command_id, body["barrier_id"])
        ack = self._client.post(
            f"{self._base}/{self._uid}/commands/{command_id}/ack",
            json={
                "lease_token": body["lease_token"],
                "result": {"opened": relay_result.opened},
            },
        )
        ack_body = ack.json() if ack.status_code == 200 else {}
        return ProcessOutcome(
            command_id=command_id,
            relay_opened=relay_result.opened,
            relay_deduplicated=relay_result.deduplicated,
            acked=ack.status_code == 200,
            ack_replayed=bool(ack_body.get("replayed", False)),
        )
