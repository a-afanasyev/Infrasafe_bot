"""Действия исполнителя «простого режима»: «Готово» с фото и «Проблема».

Отдельный модуль, а не `router.py`: тот уже на пределе размера, а эти два
эндпоинта — самостоятельная поверхность TWA (план «Простой режим
исполнителя», Фаза 1). Префикс тот же — `/api/v2/requests` (заявлен в
edge-allowlist обеих площадок). Логика — в сервисах
(`services/executor_completion`, `services/executor_problem`); здесь только
HTTP: роли, парсинг, маппинг отказов, post-commit.
"""
from __future__ import annotations

from fastapi import (
    APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Request, UploadFile,
)
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.api.dependencies import get_db, require_roles
from uk_management_bot.api.dependencies_access import is_assigned_executor
from uk_management_bot.api.rate_limit import limiter
from uk_management_bot.api.requests import service as svc
from uk_management_bot.api.requests.problem_notify import notify_managers_problem_detached
from uk_management_bot.api.requests.router import _card
from uk_management_bot.api.requests.schemas import CommentOut, ProblemBody, RequestCard
from uk_management_bot.database.models.user import User
from uk_management_bot.database.session import AsyncSessionLocal
from uk_management_bot.services.executor_completion import (
    COMPLETION_PHOTO_MAX_BYTES,
    CompletionRefused,
    complete_with_photo,
)
from uk_management_bot.services.executor_problem import problem_comment_text
from uk_management_bot.services.redis_pubsub import publish_request_event
from uk_management_bot.services.workflow_notifications import (
    dispatch_notify_intents_detached,
)
from uk_management_bot.utils.constants import COMMENT_TYPE_PROBLEM
from uk_management_bot.utils.request_workflow import TERMINAL_STATUSES, normalize_status

router = APIRouter()

# Загрузка фото тяжелее обычного PATCH; 20/мин на исполнителя — с запасом на
# повторы после таймаута (они идемпотентны), но не для перебора.
COMPLETE_RATE_LIMIT = "20/minute"
PROBLEM_RATE_LIMIT = "30/minute"


async def _fresh_card(db: AsyncSession, request_number: str, user: User) -> RequestCard:
    row = await svc.request_with_executor(db, request_number)
    if row is None:
        raise HTTPException(status_code=404, detail="Request not found")
    req, exec_user = row
    return await _card(db, req, exec_user, user)


@router.post("/{request_number}/complete", response_model=RequestCard)
@limiter.limit(COMPLETE_RATE_LIMIT)
async def complete_request(
    request: Request,
    request_number: str,
    background: BackgroundTasks,
    photo: UploadFile = File(..., description="Фото «после»: JPEG/PNG, до 8 МиБ"),
    idempotency_key: str = Form(..., description="UUID попытки; повтор с ним же безопасен"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("executor")),
):
    """«Готово»: одно фото «после» → заявка «Выполнена» (EXECUTOR_COMPLETE).

    Фото уходит в media-service ДО перехода; сбой загрузки статус не меняет.
    Повтор с тем же `idempotency_key` (и повтор по уже закрытой этим же
    исполнителем заявке) — 200 с карточкой без второй загрузки.

    Ответы: 200 — карточка; 403 `not_assigned` / `no_active_shift`;
    404; 409 `invalid_status` / `in_progress`; 413 `photo_too_large`;
    415 `unsupported_photo_type`; 422 `photo_empty` / `invalid_idempotency_key`;
    502 `media_rejected`; 503 `media_unavailable`.
    """
    # Читаем не больше лимита + 1 байт: этого хватает, чтобы понять «больше».
    photo_bytes = await photo.read(COMPLETION_PHOTO_MAX_BYTES + 1)
    # Сессия запроса (autobegin от auth) не должна висеть idle-in-transaction,
    # пока идёт загрузка в media-service: сервис открывает свои сессии.
    await db.close()
    try:
        result = await complete_with_photo(
            AsyncSessionLocal, request_number, user.id, photo_bytes, idempotency_key)
    except CompletionRefused as exc:
        raise HTTPException(status_code=exc.http_status, detail=exc.code)

    outcome = result.outcome
    if outcome is not None:
        for ev in outcome.post_commit_intents:
            if ev.kind == "realtime":
                await publish_request_event("request.status_changed", {
                    "number": request_number,
                    "old_status": normalize_status(outcome.old_state),
                    "new_status": ev.data.get("status"),
                })
        background.add_task(
            dispatch_notify_intents_detached, request_number, outcome.post_commit_intents)
    return await _fresh_card(db, request_number, user)


@router.post("/{request_number}/problem", response_model=CommentOut, status_code=201)
@limiter.limit(PROBLEM_RATE_LIMIT)
async def report_problem(
    request: Request,
    request_number: str,
    body: ProblemBody,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("executor")),
):
    """«Проблема»: комментарий исполнителя по шаблону, статус не меняется.

    Отдельный эндпоинт, а не поле в `POST /comments`: тот открыт всем, у кого
    есть доступ к заявке, и никого не уведомляет; «Проблема» — только
    назначенному исполнителю и всегда с уведомлением менеджерам.

    Ответы: 201 — комментарий (`comment_type="problem"`); 403 — не твоя
    заявка; 404; 409 — заявка финализирована; 422 — шаблон/текст.
    """
    req = await svc.request_by_number(db, request_number)
    if req is None:
        raise HTTPException(status_code=404, detail="Request not found")
    assignments = await svc.assignments_for(db, request_number)
    if not is_assigned_executor(req, user, assignments):
        raise HTTPException(status_code=403, detail="not_assigned")
    if normalize_status(req) in TERMINAL_STATUSES:
        raise HTTPException(status_code=409, detail="invalid_status")

    comment = await svc.create_comment(
        db,
        request_number=request_number,
        user_id=user.id,
        text=problem_comment_text(body.template, body.text),
        is_internal=False,
        comment_type=COMMENT_TYPE_PROBLEM,
    )
    background.add_task(
        notify_managers_problem_detached, request_number, user.id, body.template, body.text)
    return comment
