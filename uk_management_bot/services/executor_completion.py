"""Атомарное «Готово» исполнителя: одно фото «после» → заявка «Выполнена».

Решение владельца (план «Простой режим исполнителя»): «Готово» = ровно одно
фото «после», текст не нужен. Прежний TWA-путь сначала закрывал заявку PATCH'ем,
потом грузил фото по одному без ретраев — фото терялись, заявка оставалась
закрытой без фотоотчёта. Здесь порядок обратный и сведён в одну точку,
общую для API и (Фаза 4) бота:

1. фото проверяется локально (размер под лимит edge, тип по magic bytes);
2. сухой прогон канона (`preflight_command_async`) — тот же предикат
   EXECUTOR_COMPLETE; отказ ДО загрузки, чтобы не вешать фото на заявку,
   которую нельзя закрыть;
3. фото уходит в media-service категорией ``completion_photo`` — тем же
   клиентом и эндпоинтом (`/media/upload-report`), что у бота; SSOT фотоотчёта
   — media-service (`services/completion_media`), legacy-поле
   `completion_media` не пишется, как и в TWA-пути. Сбой → статус не меняется;
4. EXECUTOR_COMPLETE через `run_command_async`.

Сбой шага 4 после успешного шага 3: фото остаётся в media-service привязанным
к заявке (это фото работ, оно не вредит), а запись идемпотентности хранит его
``media_id`` со стадией ``uploaded`` — повтор с тем же ключом НЕ грузит фото
заново и сразу выполняет шаг 4. Идемпотентность и её поведение при сбое
Redis — `services/completion_idempotency`.

Сервис не знает про HTTP: отказ — `CompletionRefused(code, http_status)`,
статус — рекомендация адаптеру (API маппит 1:1, бот — в текст).
"""
from __future__ import annotations

import io
import logging
import uuid
from dataclasses import dataclass
from typing import Optional

import httpx

from uk_management_bot.integrations import get_media_client
from uk_management_bot.services import completion_idempotency as idem
from uk_management_bot.services.request_media_markers import extract_media_id
from uk_management_bot.services.workflow_runner import (
    CommandOutcome,
    RequestNotFound,
    preflight_command_async,
    run_command_async,
)
from uk_management_bot.utils.constants import REQUEST_STATUS_EXECUTED
from uk_management_bot.utils.http_errors import describe_http_error
from uk_management_bot.utils.media_sniff import (
    MEDIA_SERVICE_ACCEPTED_TYPES,
    sniff_media_mime,
)
from uk_management_bot.utils.request_workflow import (
    Action,
    ActionCommand,
    InvalidTransition,
    NotAuthorized,
    PrincipalRef,
    RepeatConflict,
    RepeatRejected,
    WorkflowError,
    normalize_status,
)
from uk_management_bot.utils.request_workflow.guards import _is_assigned_executor

logger = logging.getLogger(__name__)

# Edge (profk nginx) режет тело запроса на 10 МБ, и 413 оттуда не доходит до
# логов API. 8 МиБ + multipart-обвязка пролезают, и это же PUBLIC_MEDIA_MAX_BYTES
# витрины отчётов — кадр попадёт и в отчёт «до/после». TWA и так ужимает
# фото до 1600px JPEG (`twa/utils/downscaleImage.ts`).
COMPLETION_PHOTO_MAX_BYTES = 8 * 1024 * 1024
# webp/heic сниффер распознаёт, но media-service их не хранит (BUG-132).
COMPLETION_PHOTO_TYPES = frozenset({"image/jpeg", "image/png"}) & MEDIA_SERVICE_ACCEPTED_TYPES
_EXTENSIONS = {"image/jpeg": "jpg", "image/png": "png"}

# Ответ обязан успеть раньше, чем edge отдаст 504 (30 с, BUG-189). POST не
# ретраится: он не идемпотентен на стороне media-service — повтор клиента
# закрывает запись идемпотентности.
UPLOAD_TIMEOUT = httpx.Timeout(connect=5.0, read=25.0, write=5.0, pool=5.0)

COMPLETION_CATEGORY = "completion_photo"


class CompletionRefused(Exception):
    """Отказ завершить заявку: машинный код + рекомендуемый HTTP-статус."""

    def __init__(self, code: str, http_status: int):
        super().__init__(code)
        self.code = code
        self.http_status = http_status


@dataclass(frozen=True)
class CompletionResult:
    request_number: str
    media_id: Optional[int]
    # None — переход в этом вызове не выполнялся (повтор / уже закрыта им же):
    # post-commit (уведомления, realtime) адаптеру делать нечего.
    outcome: Optional[CommandOutcome]

    @property
    def replayed(self) -> bool:
        return self.outcome is None


def validate_completion_photo(photo_bytes: bytes) -> str:
    """Server-derived MIME фото «после» или отказ. Клиентскому типу не верим (H2)."""
    if not photo_bytes:
        raise CompletionRefused("photo_empty", 422)
    if len(photo_bytes) > COMPLETION_PHOTO_MAX_BYTES:
        raise CompletionRefused("photo_too_large", 413)
    mime = sniff_media_mime(photo_bytes)
    if mime not in COMPLETION_PHOTO_TYPES:
        raise CompletionRefused("unsupported_photo_type", 415)
    return mime


def parse_idempotency_key(raw: Optional[str]) -> str:
    try:
        return str(uuid.UUID(str(raw or "").strip()))
    except ValueError:
        raise CompletionRefused("invalid_idempotency_key", 422) from None


def _command(request_number: str, key: str) -> ActionCommand:
    # Текст отчёта не нужен (решение владельца); completion_media не пишем —
    # SSOT фотоотчёта media-service.
    return ActionCommand(command_id=f"api:{request_number}:complete:{key}",
                         action=Action.EXECUTOR_COMPLETE, payload={})


def _completed_by(snapshot, executor_id: int) -> bool:
    """Естественная идемпотентность: заявка уже «Выполнена» этим исполнителем."""
    return (normalize_status(snapshot.request) == REQUEST_STATUS_EXECUTED
            and snapshot.request.executor_id == executor_id)


def _refusal(error: WorkflowError, snapshot, actor) -> CompletionRefused:
    if isinstance(error, NotAuthorized):
        if snapshot is not None and actor is not None and _is_assigned_executor(snapshot, actor):
            # Своя заявка, но предикат не пустил — единственная причина у
            # EXECUTOR_COMPLETE для назначенного исполнителя: нет активной смены.
            return CompletionRefused("no_active_shift", 403)
        return CompletionRefused("not_assigned", 403)
    if isinstance(error, (InvalidTransition, RepeatRejected, RepeatConflict)):
        return CompletionRefused("invalid_status", 409)
    return CompletionRefused("workflow_error", 422)


async def _preflight(session_factory, request_number: str, principal: PrincipalRef,
                     command: ActionCommand, executor_id: int) -> bool:
    """True — заявка уже закрыта этим исполнителем; отказ — CompletionRefused."""
    try:
        pre = await preflight_command_async(session_factory, request_number, principal, command)
    except RequestNotFound:
        raise CompletionRefused("not_found", 404) from None
    except NotAuthorized as exc:  # неизвестный пользователь — до снимка
        raise _refusal(exc, None, None) from None
    if pre.error is None:
        return False
    if _completed_by(pre.snapshot, executor_id):
        return True
    raise _refusal(pre.error, pre.snapshot, pre.actor)


async def _upload(request_number: str, executor_id: int, photo_bytes: bytes, mime: str) -> int:
    client = get_media_client()
    if client is None:
        raise CompletionRefused("media_unavailable", 503)
    try:
        result = await client.upload_report_media(
            request_number=request_number,
            file_path=io.BytesIO(photo_bytes),
            filename=f"{request_number}_after.{_EXTENSIONS[mime]}",
            report_type=COMPLETION_CATEGORY,
            uploaded_by=executor_id,
            content_type=mime,
            timeout=UPLOAD_TIMEOUT,
        )
    except httpx.HTTPStatusError as exc:
        logger.error("complete %s: media-service отверг фото: %s",
                     request_number, describe_http_error(exc))
        status = exc.response.status_code if exc.response is not None else 503
        raise CompletionRefused(
            "media_unavailable" if status >= 500 else "media_rejected",
            503 if status >= 500 else 502) from None
    except Exception as exc:  # noqa: BLE001 — сеть/таймаут/прочее = сервис недоступен
        logger.error("complete %s: загрузка фото не удалась: %s",
                     request_number, describe_http_error(exc))
        raise CompletionRefused("media_unavailable", 503) from None
    media_id = extract_media_id(result)
    if media_id is None:
        logger.error("complete %s: ответ media-service без media_file.id", request_number)
        raise CompletionRefused("media_rejected", 502)
    return media_id


async def _transition(session_factory, request_number: str, principal: PrincipalRef,
                      command: ActionCommand, executor_id: int) -> Optional[CommandOutcome]:
    """EXECUTOR_COMPLETE; None — гонка, заявку уже закрыл этот же исполнитель."""
    try:
        return await run_command_async(session_factory, request_number, principal, command)
    except RequestNotFound:
        raise CompletionRefused("not_found", 404) from None
    except WorkflowError as exc:
        pre = await preflight_command_async(session_factory, request_number, principal, command)
        if _completed_by(pre.snapshot, executor_id):
            return None
        raise _refusal(exc, pre.snapshot, pre.actor) from None


async def complete_with_photo(session_factory, request_number: str, executor_id: int,
                              photo_bytes: bytes, idempotency_key: str, *,
                              source: str = "api") -> CompletionResult:
    """Закрыть заявку фото «после» атомарно и идемпотентно (см. докстринг модуля)."""
    key = parse_idempotency_key(idempotency_key)
    mime = validate_completion_photo(photo_bytes)

    record = await idem.load(executor_id, request_number, key)
    if record is not None and record.state == idem.STATE_DONE:
        return CompletionResult(request_number, record.media_id, None)

    lock = await idem.acquire_lock(request_number)
    if not lock.acquired:
        raise CompletionRefused("in_progress", 409)
    try:
        principal = PrincipalRef(kind="user", user_id=executor_id, source=source)
        command = _command(request_number, key)
        if await _preflight(session_factory, request_number, principal, command, executor_id):
            media_id = record.media_id if record is not None else None
            await idem.save(executor_id, request_number, key, idem.STATE_DONE, media_id)
            return CompletionResult(request_number, media_id, None)

        if record is not None and record.state == idem.STATE_UPLOADED and record.media_id:
            media_id = record.media_id  # фото уже в заявке, сбой был на шаге 4
        else:
            media_id = await _upload(request_number, executor_id, photo_bytes, mime)
            await idem.save(executor_id, request_number, key, idem.STATE_UPLOADED, media_id)

        outcome = await _transition(session_factory, request_number, principal, command, executor_id)
        await idem.save(executor_id, request_number, key, idem.STATE_DONE, media_id)
        return CompletionResult(request_number, media_id, outcome)
    finally:
        await idem.release_lock(lock)
