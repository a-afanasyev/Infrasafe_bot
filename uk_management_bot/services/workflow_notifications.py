"""Исполнение `notify`-интентов канонического движка (адресные уведомления).

Зачем модуль появился (прод-жалоба 2026-07-25): житель не получал уведомления
об уточнении. Оказалось, что дело не в уточнении — движок выпускает интент
`notify` на КАЖДЫЙ переход (`request_workflow._build_events`), но исполнял его
только бот, да и то вручную внутри своего хендлера. В API-роутере цикл разбора
`post_commit_intents` обрабатывал только `realtime`, а `notify` молча
выбрасывался — значит ни один переход, сделанный из дашборда, никого не
уведомлял.

AUD6-P1-6 (2026-07-30): теперь матрицу исполняют ОБА пути. Бот-хендлеры после
`run_command_sync` зовут `dispatch_notify_intents_sync` (sync-сессия бота +
явный bot-инстанс) вместо легаси `async_notify_request_status_changed`,
которое на одни и те же переходы слало других получателей с другим текстом.
Канальная лента из легаси сохранена ОТДЕЛЬНЫМ хелпером
`notify_channel_status_changed`: матрица — адресная, канал — другая
поверхность, и снятие легаси без него молча убило бы канал.

Почему не «слать на всё подряд»: интент выпускается и на служебные переходы
(взятие из пула, авто-промоут, разрешение уточнения). Уведомление на каждый —
это спам, после которого их перестают читать. Здесь ЯВНЫЙ список действий, где
получатель обязан что-то узнать или сделать, согласованный с владельцем:
уточнение, назначение исполнителя, готовность к приёмке, возврат менеджером в
работу, возврат жителем из приёмки, отмена.

Best-effort по построению: уведомление — не часть транзакции перехода. Переход
уже закоммичен, и упавшая отправка не должна ни откатывать его, ни ронять ответ
API. Все исключения гасятся и логируются.

A6-P2-07: подстановки `address`/`category`/`clarification_text` — свободный
пользовательский текст, а оба зарегистрированных бота работают в
`parse_mode=HTML`. Без `html.escape` адрес с `<`, `>` или `&` давал Telegram
400 «can't parse entities», и уведомление молча терялось — ровно та жалоба,
ради которой модуль писался.
"""

import html
import logging
from typing import Iterable, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

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
    # AUD6-P1-6: возврат ЖИТЕЛЕМ из приёмки — симметрия с возвратом менеджера:
    # исполнитель обязан узнать, что работу переделывать. До этой строки на
    # API/TWA-пути возврат жителя не уведомлял никого (бот слал через легаси).
    Action.APPLICANT_RETURN: ((EXECUTOR,), "notifications.workflow.returned_to_work"),
    Action.CANCEL: ((APPLICANT,), "notifications.workflow.cancelled"),
}

# Богатый шаблон уточнения: несёт сам текст вопроса и команду ответа. Ключ
# исторически ботовский, но с AUD6-P1-6 им пользуются оба пути — вопрос
# менеджера обязан доехать до жителя независимо от поверхности, где его задали.
_CLARIFY_RICH_KEY = "admin.handlers.notify_user_clarification"


def _plan(intents: Iterable) -> list[tuple[Action, tuple[str, ...], str]]:
    """Отфильтровать интенты до плана рассылки (чистая часть, общая обоим путям)."""
    plan: list[tuple[Action, tuple[str, ...], str]] = []
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
        plan.append((action, spec[0], spec[1]))
    return plan


def _render_text(
    action: Action,
    text_key: str,
    language: str,
    request: Request,
    clarification_text: Optional[str],
) -> str:
    """Текст для получателя. Пользовательские подстановки — через html.escape."""
    if action is Action.CLARIFY_REQUEST and clarification_text:
        # Подпись категории — обычно наша словарная (безопасная), но fallback
        # get_category_display для НЕИЗВЕСТНОГО ключа возвращает сырое значение
        # из БД как есть (security-review PR #305, borderline): у legacy-заявки
        # категория с '<'/'&' роняла бы отправку Telegram-400. escape нейтрален
        # для словарных подписей и закрывает fallback.
        from uk_management_bot.keyboards.requests import (
            get_category_display, resolve_category_key,
        )
        return get_text(
            _CLARIFY_RICH_KEY,
            language=language,
            request_number=request.request_number,
            category=html.escape(get_category_display(
                resolve_category_key(request.category), language=language
            )),
            address=html.escape(request.address or ""),
            clarification_text=html.escape(clarification_text),
        )
    return get_text(
        text_key,
        language=language,
        request_number=request.request_number,
        address=html.escape(request.address or ""),
        category=html.escape(request.category or ""),
    )


def _wanted_user_ids(request: Request, roles: Iterable[str]) -> set[int]:
    wanted = set()
    for role in roles:
        if role == APPLICANT and request.user_id:
            wanted.add(request.user_id)
        elif role == EXECUTOR and request.executor_id:
            wanted.add(request.executor_id)
    return wanted


async def _send_to_recipients(
    bot,
    request: Request,
    recipients: list[User],
    action: Action,
    text_key: str,
    clarification_text: Optional[str],
) -> int:
    from uk_management_bot.services.notification_service import send_to_user

    sent = 0
    for user in recipients:
        # Язык получателя, а не актора: сообщение читает он.
        text = _render_text(
            action, text_key, user.language or "ru", request, clarification_text
        )
        if await send_to_user(bot, user.telegram_id, text):
            sent += 1
    return sent


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
    wanted_ids = _wanted_user_ids(request, roles)
    if not wanted_ids:
        return request, []
    users = (
        await db.execute(select(User).where(User.id.in_(wanted_ids)))
    ).scalars().all()
    return request, [u for u in users if u.telegram_id]


def _load_recipients_sync(
    db: Session, request_number: str, roles: Iterable[str]
) -> tuple[Optional[Request], list[User]]:
    """Sync-зеркало `_load_recipients` для бот-пути (сессии бота синхронные)."""
    request = (
        db.execute(select(Request).where(Request.request_number == request_number))
    ).scalar_one_or_none()
    if request is None:
        return None, []
    wanted_ids = _wanted_user_ids(request, roles)
    if not wanted_ids:
        return request, []
    users = (
        db.execute(select(User).where(User.id.in_(wanted_ids)))
    ).scalars().all()
    return request, [u for u in users if u.telegram_id]


async def dispatch_notify_intents(
    db: AsyncSession,
    request_number: str,
    intents: Iterable,
    clarification_text: Optional[str] = None,
) -> int:
    """Разослать адресные уведомления по `notify`-интентам (API-путь). Не бросает.

    Возвращает число фактически доставленных сообщений — для логов и тестов.
    """
    from uk_management_bot.services.notification_service import _get_shared_bot

    sent = 0
    for action, roles, text_key in _plan(intents):
        try:
            request, recipients = await _load_recipients(db, request_number, roles)
            if request is None or not recipients:
                continue
            sent += await _send_to_recipients(
                _get_shared_bot(), request, recipients, action, text_key,
                clarification_text,
            )
        except Exception as e:
            # Переход уже закоммичен — сбой рассылки не имеет права его тронуть
            # или уронить ответ API.
            logger.warning(
                "Уведомление по действию %s для заявки %s не отправлено: %s",
                action.value, request_number, e,
            )
    return sent


async def dispatch_notify_intents_sync(
    db: Session,
    request_number: str,
    intents: Iterable,
    bot=None,
    clarification_text: Optional[str] = None,
) -> int:
    """Тот же диспетчер для бот-пути: sync-сессия + явный bot из хендлера.

    Матрица, тексты и получатели общие с API-путём (`_plan`/`_render_text`/
    `_send_to_recipients`) — расходиться им больше негде. Не бросает.
    """
    from uk_management_bot.services.notification_service import _get_shared_bot

    sent = 0
    for action, roles, text_key in _plan(intents):
        try:
            request, recipients = _load_recipients_sync(db, request_number, roles)
            if request is None or not recipients:
                continue
            sent += await _send_to_recipients(
                bot or _get_shared_bot(), request, recipients, action, text_key,
                clarification_text,
            )
        except Exception as e:
            logger.warning(
                "Уведомление по действию %s для заявки %s не отправлено: %s",
                action.value, request_number, e,
            )
    return sent


async def notify_channel_status_changed(
    bot, request: Optional[Request], old_status: str, new_status: str
) -> None:
    """Канальная лента смены статуса — то, что НЕ покрывает адресная матрица.

    Легаси `async_notify_request_status_changed` слал заявителю, исполнителю И
    в канал; адресную часть заменила матрица интентов, канальная сохранена
    здесь — иначе снятие легаси с бот-хендлеров молча убило бы канал. Тот же
    best-effort: не бросает.
    """
    if request is None:
        return
    from uk_management_bot.services.notification_service import (
        _build_request_status_message_channel, send_to_channel,
    )

    try:
        await send_to_channel(
            bot, _build_request_status_message_channel(request, old_status, new_status)
        )
    except Exception as e:
        logger.warning(
            "Канальное уведомление по заявке %s не отправлено: %s",
            getattr(request, "request_number", "?"), e,
        )
