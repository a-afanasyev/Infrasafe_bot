"""Исполнение `notify`-интентов канонического движка (адресные уведомления).

Зачем модуль появился (прод-жалоба 2026-07-25): житель не получал уведомления
об уточнении. Оказалось, что дело не в уточнении — движок выпускает интент
`notify` на КАЖДЫЙ переход (`request_workflow._build_events`), но исполнял его
только бот, да и то вручную внутри своего хендлера
(`handlers/admin/actions.py` шлёт сообщение сам, минуя интент). В API-роутере
цикл разбора `post_commit_intents` обрабатывал только `realtime`, а `notify`
молча выбрасывался — значит ни один переход, сделанный из дашборда, никого не
уведомлял.

Почему не «слать на всё подряд»: интент выпускается и на служебные переходы
(взятие из пула, авто-промоут, разрешение уточнения). Уведомление на каждый —
это спам, после которого их перестают читать. Здесь ЯВНЫЙ список действий, где
получатель обязан что-то узнать или сделать, согласованный с владельцем:
уточнение, назначение исполнителя, готовность к приёмке, возврат менеджером в
работу, отмена.

Best-effort по построению: уведомление — не часть транзакции перехода. Переход
уже закоммичен, и упавшая отправка не должна ни откатывать его, ни ронять ответ
API. Все исключения гасятся и логируются.

⚠️ Двойной отправки с ботом нет: бот-хендлеры зовут `run_command_sync` и
интенты не разбирают вовсе. Если когда-нибудь начнут — сначала убрать inline-
отправку из `handlers/admin/actions.py`, иначе житель получит два сообщения.
"""

import logging
from typing import Iterable, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.user import User
from uk_management_bot.utils.helpers import get_text
from uk_management_bot.utils.request_workflow import Action

logger = logging.getLogger(__name__)

# Кому адресовано уведомление.
APPLICANT = "applicant"
EXECUTOR = "executor"

# action → (получатели, i18n-ключ). Ключи лежат в config/locales/{ru,uz}.json
# под `notifications.workflow.*` и получают request_number/category/address.
#
# Осознанно НЕ уведомляем: EXECUTOR_CLAIM (исполнитель сам взял — он и так
# знает), SYSTEM_AUTO_PROMOTE и прочие служебные, CLARIFY_RESOLVED (ответ на
# уточнение приходит тем же диалогом), APPLICANT_ACCEPT (житель сам принял).
_NOTIFY_MATRIX: dict[Action, tuple[tuple[str, ...], str]] = {
    # Уточнение — исходная жалоба: житель ждёт ответа и должен узнать вопрос.
    Action.CLARIFY_REQUEST: ((APPLICANT,), "notifications.workflow.clarify_request"),
    # Назначение: исполнителю — новая работа, жителю — «работы начались».
    Action.MANAGER_ASSIGN: ((APPLICANT, EXECUTOR), "notifications.workflow.assigned"),
    # Готовность к приёмке — единственное действие, которого ЖДУТ от жителя.
    Action.EXECUTOR_COMPLETE: ((APPLICANT,), "notifications.workflow.executed"),
    Action.MANAGER_COMPLETE: ((APPLICANT,), "notifications.workflow.executed"),
    Action.MANAGER_CONFIRM: ((APPLICANT,), "notifications.workflow.ready_for_acceptance"),
    # Возврат менеджером в работу: исполнителю — переделывать, жителю — статус.
    Action.MANAGER_RETURN_TO_WORK: (
        (APPLICANT, EXECUTOR), "notifications.workflow.returned_to_work"),
    Action.CANCEL: ((APPLICANT,), "notifications.workflow.cancelled"),
}


async def _load_recipients(
    db: AsyncSession, request_number: str, roles: Iterable[str]
) -> tuple[Optional[Request], list[User]]:
    """Заявка + пользователи-получатели (только с telegram_id)."""
    request = (
        await db.execute(
            select(Request).where(Request.request_number == request_number)
        )
    ).scalar_one_or_none()
    if request is None:
        return None, []

    wanted_ids = []
    for role in roles:
        if role == APPLICANT and request.user_id:
            wanted_ids.append(request.user_id)
        elif role == EXECUTOR and request.executor_id:
            wanted_ids.append(request.executor_id)
    if not wanted_ids:
        return request, []

    users = (
        await db.execute(select(User).where(User.id.in_(set(wanted_ids))))
    ).scalars().all()
    return request, [u for u in users if u.telegram_id]


async def dispatch_notify_intents(
    db: AsyncSession, request_number: str, intents: Iterable
) -> int:
    """Разослать адресные уведомления по `notify`-интентам. Не бросает.

    Возвращает число фактически доставленных сообщений — для логов и тестов.
    """
    from uk_management_bot.services.notification_service import (
        _get_shared_bot, send_to_user,
    )

    sent = 0
    for intent in intents:
        if getattr(intent, "kind", None) != "notify":
            continue
        raw_action = (intent.data or {}).get("action")
        try:
            action = Action(raw_action)
        except ValueError:
            continue
        spec = _NOTIFY_MATRIX.get(action)
        if spec is None:
            # Служебный переход — молчим (см. docstring модуля).
            continue
        roles, text_key = spec

        try:
            request, recipients = await _load_recipients(db, request_number, roles)
            if request is None or not recipients:
                continue
            bot = _get_shared_bot()
            for user in recipients:
                # Язык получателя, а не актора: сообщение читает он.
                text = get_text(
                    text_key,
                    language=user.language or "ru",
                    request_number=request.request_number,
                    address=request.address or "",
                    category=request.category or "",
                )
                if await send_to_user(bot, user.telegram_id, text):
                    sent += 1
        except Exception as e:
            # Переход уже закоммичен — сбой рассылки не имеет права его тронуть
            # или уронить ответ API.
            logger.warning(
                "Уведомление по действию %s для заявки %s не отправлено: %s",
                raw_action, request_number, e,
            )
    return sent
