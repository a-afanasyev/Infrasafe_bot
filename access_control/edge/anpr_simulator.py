"""ANPR-симулятор edge (§14.2 п.4): синтетические события + валидная device-auth подпись.

Генерит СИНТЕТИЧЕСКИЕ ANPR-события (§11 — реальные ПД не используются) и шлёт их на
``POST /api/v1/access/camera-events/anpr`` с корректной device-auth подписью (тот же
канонический стринг/HMAC, что проверяет backend в ``services/device_auth``). Полезен
для e2e-проверки полного контура «камера → решение → команда».

Клиент duck-typed (``.post`` с ``content=``/``headers=``): TestClient в тестах или
прод-edge HTTP. Секрет резолвится так же, как backend — из ``controller_uid`` (пилот).
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import random
from typing import Any
from urllib.parse import urlsplit

from access_control.domain.enums import Direction, EventSource
from access_control.services.device_auth import resolve_device_secret, sign_request

# Путь приёма ANPR (§13.1). Симулятор подписывает именно этот path.
ANPR_PATH = "/api/v1/access/camera-events/anpr"

# Алфавит синтетических UZ-подобных номеров (§11 — синтетика, не реальные ПД).
_DIGITS = "0123456789"
_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


class AnprSimulator:
    """Edge-симулятор ANPR: строит синтетическое событие и шлёт подписанный запрос.

    ``client`` — HTTP-клиент (TestClient/прод-edge), ``controller_uid`` — идентичность
    устройства device-auth, остальное — топология пилотной точки (зона/точка/камера/
    шлагбаум). ``api_key`` по умолчанию — пилотный ключ устройства.
    """

    def __init__(
        self,
        client: Any,
        *,
        controller_uid: str,
        zone_id: int,
        gate_id: int,
        camera_id: int,
        barrier_id: int,
        api_key: str = "pilot-test-device-key",
        seed: int | None = None,
    ) -> None:
        self._client = client
        self._uid = controller_uid
        self._zone_id = zone_id
        self._gate_id = gate_id
        self._camera_id = camera_id
        self._barrier_id = barrier_id
        self._api_key = api_key
        self._secret = resolve_device_secret(controller_uid)
        self._rng = random.Random(seed)

    def random_plate(self) -> str:
        """Синтетический номер вида ``01A234BC`` (§11 — только синтетика, не ПД)."""
        region = "".join(self._rng.choice(_DIGITS) for _ in range(2))
        l1 = self._rng.choice(_LETTERS)
        digits = "".join(self._rng.choice(_DIGITS) for _ in range(3))
        l2 = "".join(self._rng.choice(_LETTERS) for _ in range(2))
        return f"{region}{l1}{digits}{l2}"

    def _event_id(self, plate: str, captured_at: dt.datetime) -> str:
        """Детерминированный event_id (решение CTO #1): хэш controller|gate|plate|bucket."""
        bucket = int(captured_at.timestamp())
        raw = f"{self._uid}|{self._gate_id}|{plate}|{bucket}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]

    def build_event(
        self,
        plate: str,
        *,
        event_id: str | None = None,
        captured_at: dt.datetime | None = None,
        direction: str = Direction.ENTRY.value,
        confidence: float = 0.95,
    ) -> dict:
        """Сформировать ANPR-DTO (как ожидает endpoint §13.1). Синтетический (§11)."""
        cap = captured_at or dt.datetime.now(dt.timezone.utc)
        return {
            "controller_uid": self._uid,
            "event_id": event_id or self._event_id(plate, cap),
            "zone_id": self._zone_id,
            "gate_id": self._gate_id,
            "camera_id": self._camera_id,
            "barrier_id": self._barrier_id,
            "plate_number": plate,
            "direction": direction,
            "source": EventSource.CONNECTED.value,
            "confidence": confidence,
            "captured_at": cap.isoformat(),
        }

    def send(
        self,
        *,
        plate: str | None = None,
        event_id: str | None = None,
        captured_at: dt.datetime | None = None,
        direction: str = Direction.ENTRY.value,
        confidence: float = 0.95,
    ):
        """Подписать и отправить синтетическое ANPR-событие; вернуть HTTP-ответ.

        Тело сериализуется детерминированно и отправляется как ``content=`` —
        подписанные байты в точности совпадают с отправленными (HMAC body, §9.1).
        """
        plate = plate or self.random_plate()
        event = self.build_event(
            plate,
            event_id=event_id,
            captured_at=captured_at,
            direction=direction,
            confidence=confidence,
        )
        body = json.dumps(event).encode("utf-8")
        path = urlsplit(ANPR_PATH).path
        headers = sign_request(
            "POST",
            path,
            body,
            controller_uid=self._uid,
            api_key=self._api_key,
            secret=self._secret,
        )
        headers["content-type"] = "application/json"
        return self._client.post(ANPR_PATH, content=body, headers=headers)

    def send_photos(
        self,
        *,
        event_id: str,
        plate_bytes: bytes | None = None,
        overview_bytes: bytes | None = None,
    ):
        """Дослать синтетические фото проезда на photos-эндпоинт ПОСЛЕ решения (§10.2).

        Сквозной синтетический путь (§11 — только синтетические байты, не реальные
        ПД): подписывает multipart device-auth и шлёт на
        ``/edge/{controller_uid}/camera-events/{event_id}/photos``. Тело multipart
        строится один раз (фиксированный boundary) — подписанные байты совпадают с
        отправленными (HMAC body, §9.1). Минимум один из ``plate_bytes``/
        ``overview_bytes`` должен быть задан.
        """
        import httpx

        files: dict[str, tuple[str, bytes, str]] = {}
        if plate_bytes is not None:
            files["plate"] = ("plate.jpg", plate_bytes, "image/jpeg")
        if overview_bytes is not None:
            files["overview"] = ("overview.jpg", overview_bytes, "image/jpeg")
        if not files:
            raise ValueError("send_photos: нужно хотя бы одно фото (plate/overview)")

        path = f"/api/v1/access/edge/{self._uid}/camera-events/{event_id}/photos"
        req = httpx.Request("POST", "http://testserver" + path, files=files)
        body = req.read()
        headers = sign_request(
            "POST",
            path,
            body,
            controller_uid=self._uid,
            api_key=self._api_key,
            secret=self._secret,
        )
        headers["content-type"] = req.headers["content-type"]
        return self._client.post(path, content=body, headers=headers)
