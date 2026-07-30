"""Автозаполнение и ручная валидация медиа отчёта: `fetch_media_selection` /
`apply_media_selection` / `autofill_media` / `validate_media_ids`."""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.config.settings import settings
from uk_management_bot.database.models.work_report import WorkReport
from uk_management_bot.services.work_reports.errors import MediaValidationError

MAX_MEDIA_PER_SIDE = 4
_AUTOFILL_FETCH_LIMIT = MAX_MEDIA_PER_SIDE * 4
_VALIDATE_FETCH_LIMIT = 200

# ===========================================================================
# autofill_media / validate_media_ids
# ===========================================================================


def _filter_and_cap(items: list[dict]) -> list[int]:
    """Молча отфильтровать неподходящие элементы и оставить первые
    MAX_MEDIA_PER_SIDE (без переупорядочивания — порядок, как вернул
    media-service)."""
    eligible = [
        item for item in items
        if item.get("file_type") == "photo"
        and item.get("status") == "active"
        and item.get("file_size") is not None
        and item["file_size"] <= settings.PUBLIC_MEDIA_MAX_BYTES
    ]
    return [item["id"] for item in eligible[:MAX_MEDIA_PER_SIDE]]


async def fetch_media_selection(
    media_client: Any, request_number: str
) -> tuple[list[int], list[int]]:
    """СЕТЕВАЯ половина автозаполнения: два GET в media-service + фильтрация.

    AUD6-P1-3: выделена из `autofill_media`, чтобы батч-вызыватели могли
    сходить в сеть ДО взятия row-лока — сеть и запись одной функцией
    вынуждали держать транзакцию с локами через HTTP-таймауты (30 с × 3
    ретрая на вызов). БД не трогает вовсе.
    """
    before_raw = await media_client.get_request_media(
        request_number, category="request_photo", limit=_AUTOFILL_FETCH_LIMIT
    )
    after_raw = await media_client.get_request_media(
        request_number, category="completion_photo", limit=_AUTOFILL_FETCH_LIMIT
    )
    return _filter_and_cap(before_raw), _filter_and_cap(after_raw)


def apply_media_selection(
    report: WorkReport, before_ids: list[int], after_ids: list[int]
) -> WorkReport:
    """ПИШУЩАЯ половина автозаполнения: мутация полей отчёта, без сети и
    без commit (транзакционные границы — на вызывающем).

    Перещёлкивает status pending<->needs_media по факту непустоты результата;
    любой другой статус (publishing/published/needs_review/rejected) не трогает.
    """
    report.before_media_ids = before_ids
    report.after_media_ids = after_ids
    report.media_synced_at = datetime.now(timezone.utc)

    # Обязателен ТОЛЬКО результат (решение владельца 2026-07-25): «до» часто
    # физически нет — житель снял уже текущее состояние, исполнитель приехал на
    # аварию без времени фотографировать. Раньше такой отчёт застревал в
    # needs_media и работа не попадала в ленту вовсе, хотя результат был.
    # Отсутствующее «до» витрина честно показывает подписью «нет фото».
    result_present = bool(report.after_media_ids)
    if not result_present and report.status == "pending":
        report.status = "needs_media"
    elif result_present and report.status == "needs_media":
        report.status = "pending"

    return report


async def autofill_media(db: AsyncSession, media_client: Any, report: WorkReport) -> WorkReport:
    """Подтянуть текущие метаданные из media-service по `report.request_number`,
    отфильтровать подходящие фото, разложить по before/after, обновить поля
    отчёта НА МЕСТЕ (мутирует и возвращает переданный объект — commit НЕ
    делает, транзакционные границы — на вызывающем).

    Композиция `fetch_media_selection` (сеть) + `apply_media_selection`
    (запись): единичным вызовам удобна одной функцией, батчи используют
    половины напрямую, чтобы не держать сеть под локом (AUD6-P1-3).

    Не доверяет никакому предыдущему состоянию `report` — всегда перечитывает
    из media-service. Молчаливая фильтрация здесь осознанна: это автоматический
    подбор из всего доступного, а не явный выбор человека (контраст —
    `validate_media_ids` ниже, который на тех же условиях REJECTS).
    """
    before_ids, after_ids = await fetch_media_selection(
        media_client, report.request_number
    )
    return apply_media_selection(report, before_ids, after_ids)


async def validate_media_ids(
    media_client: Any,
    request_number: str,
    before_media_ids: list[int],
    after_media_ids: list[int],
) -> None:
    """Проверить явно выбранные человеком id против ТЕКУЩИХ метаданных
    media-service (никогда не доверять id вслепую, даже уже выбранным ранее
    менеджером). Бросает `MediaValidationError` на первом невалидном id —
    список НЕ фильтруется и не возвращается: весь смысл — REJECT-ить
    неверный выбор человека, а не тихо его подправить (контраст с
    `autofill_media`, который фильтрует молча).

    Используется ручным PATCH и повторной проверкой перед публикацией — оба
    случая, где решение принял человек и заслуживает явного отказа.
    """
    before_actual = {
        item["id"]: item
        for item in await media_client.get_request_media(
            request_number, category="request_photo", limit=_VALIDATE_FETCH_LIMIT
        )
    }
    after_actual = {
        item["id"]: item
        for item in await media_client.get_request_media(
            request_number, category="completion_photo", limit=_VALIDATE_FETCH_LIMIT
        )
    }

    def _check(media_ids: list[int], actual: dict, side: str) -> None:
        for media_id in media_ids:
            item = actual.get(media_id)
            if item is None:
                raise MediaValidationError(
                    f"media {media_id} does not belong to request {request_number} ({side})"
                )
            if item.get("file_type") != "photo":
                raise MediaValidationError(f"media {media_id} is not a photo")
            if item.get("status") != "active":
                raise MediaValidationError(f"media {media_id} is not active")
            size = item.get("file_size")
            if size is None or size > settings.PUBLIC_MEDIA_MAX_BYTES:
                raise MediaValidationError(
                    f"media {media_id} has unknown or excessive file size"
                )

    _check(before_media_ids, before_actual, "before")
    _check(after_media_ids, after_actual, "after")
