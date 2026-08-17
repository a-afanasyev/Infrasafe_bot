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
    # То же для АВТО-назначения дежурному при создании заявки. До инварианта
    # «В работе ⟺ есть исполнитель» диспетчер назначал ГРУППУ, и заявку видели
    # все дежурные в «Свободных» — уведомлять было некого. Теперь он назначает
    # конкретного человека, и без этой строки заявка была бы назначена тому,
    # кто об этом не узнает: из пула она уже ушла (executor_id не NULL).
    Action.SYSTEM_DISPATCH_ASSIGN: (
        (APPLICANT, EXECUTOR), "notifications.workflow.assigned"),
    # Готовность к приёмке — единственное действие, которого ЖДУТ от жителя.
    Action.EXECUTOR_COMPLETE: ((APPLICANT,), "notifications.workflow.executed"),
    Action.MANAGER_COMPLETE: ((APPLICANT,), "notifications.workflow.executed"),
    Action.MANAGER_CONFIRM: ((APPLICANT,), "notifications.workflow.ready_for_acceptance"),
    # Возврат менеджером в работу: исполнителю — переделывать, жителю — статус.
    # Свой ключ (не общий с возвратом жителя): только это сообщение несёт
    # причину менеджера, и подставлять её в общий шаблон было бы нечем.
    Action.MANAGER_RETURN_TO_WORK: (
        (APPLICANT, EXECUTOR), "notifications.workflow.returned_to_work_manager"),
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
    if action is Action.MANAGER_RETURN_TO_WORK:
        # Причина обязательна на уровне ядра, но уведомление — post-commit
        # best-effort: пустая строка вместо KeyError, если запись всё же пуста
        # (легаси-заявка, вернувшаяся до этой ревизии).
        return get_text(
            text_key,
            language=language,
            request_number=request.request_number,
            address=html.escape(request.address or ""),
            category=html.escape(request.category or ""),
            reason=html.escape(getattr(request, "manager_return_reason", None) or ""),
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


async def _load_request(db: AsyncSession, request_number: str) -> Optional[Request]:
    return (
        await db.execute(
            select(Request).where(Request.request_number == request_number)
        )
    ).scalar_one_or_none()


async def _load_users(db: AsyncSession, wanted_ids: set[int]) -> list[User]:
    """Получатели с telegram_id (без него слать некуда)."""
    if not wanted_ids:
        return []
    users = (
        await db.execute(select(User).where(User.id.in_(wanted_ids)))
    ).scalars().all()
    return [u for u in users if u.telegram_id]


def _load_users_sync(db: Session, wanted_ids: set[int]) -> list[User]:
    """Sync-зеркало `_load_users` для бот-пути (сессии бота синхронные)."""
    if not wanted_ids:
        return []
    users = db.execute(select(User).where(User.id.in_(wanted_ids))).scalars().all()
    return [u for u in users if u.telegram_id]


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

    plan = _plan(intents)
    if not plan:
        return 0
    # AUD6-P2-02: заявка грузится один раз на весь набор интентов, не на каждый.
    request = await _load_request(db, request_number)
    if request is None:
        return 0
    sent = 0
    for action, roles, text_key in plan:
        try:
            recipients = await _load_users(db, _wanted_user_ids(request, roles))
            if not recipients:
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


async def dispatch_notify_intents_detached(
    request_number: str,
    intents: Iterable,
    clarification_text: Optional[str] = None,
) -> int:
    """Вариант для fastapi `BackgroundTasks` (AUD6-P2-02).

    Открывает СВОЮ короткую сессию: request-scoped к моменту исполнения фоновой
    задачи уже закрыта — а её удержание на время Telegram-отправок (таймауты в
    десятки секунд idle-in-transaction при 30/мин на ручку) и было дефектом.
    Контракт «не бросает» наследуется от dispatch_notify_intents.
    """
    from uk_management_bot.database.session import AsyncSessionLocal

    if AsyncSessionLocal is None:
        # SQLite dev-режим/тест-стенды без async-движка (session.py держит
        # AsyncSessionLocal = None) — рассылка честно пропускается, как и весь
        # async-путь в этой конфигурации.
        logger.warning(
            "notify для %s пропущен: AsyncSessionLocal недоступен (sqlite dev)",
            request_number,
        )
        return 0
    async with AsyncSessionLocal() as session:
        return await dispatch_notify_intents(
            session, request_number, intents, clarification_text=clarification_text
        )


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

    plan = _plan(intents)
    if not plan:
        return 0
    request = (
        db.execute(select(Request).where(Request.request_number == request_number))
    ).scalar_one_or_none()
    if request is None:
        return 0
    sent = 0
    for action, roles, text_key in plan:
        try:
            recipients = _load_users_sync(db, _wanted_user_ids(request, roles))
            if not recipients:
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


def collect_notify_messages_sync(
    db: Session,
    request_number: str,
    intents: Iterable,
    clarification_text: Optional[str] = None,
) -> list[tuple[int, str]]:
    """Fetch/render-фаза диспетчера для AUD3-37-конвертированных хендлеров.

    Исполняется в worker-потоке (sync-сессия под run_db): возвращает готовые
    пары (telegram_id, text) — send-фазе (``send_notify_messages``) сессия не
    нужна, Telegram-IO не держит соединение БД. Матрица, тексты и получатели —
    те же ``_plan``/``_wanted_user_ids``/``_render_text``, что у обоих
    диспетчеров выше. Best-effort по-интентно: сбой одного не валит остальные.
    """
    plan = _plan(intents)
    if not plan:
        return []
    request = (
        db.execute(select(Request).where(Request.request_number == request_number))
    ).scalar_one_or_none()
    if request is None:
        return []
    messages: list[tuple[int, str]] = []
    for action, roles, text_key in plan:
        try:
            for user in _load_users_sync(db, _wanted_user_ids(request, roles)):
                messages.append((
                    user.telegram_id,
                    _render_text(action, text_key, user.language or "ru",
                                 request, clarification_text),
                ))
        except Exception as e:
            logger.warning(
                "Уведомление по действию %s для заявки %s не собрано: %s",
                action.value, request_number, e,
            )
    return messages


async def send_notify_messages(bot, messages: list[tuple[int, str]]) -> int:
    """Send-фаза для ``collect_notify_messages_sync``. Best-effort, не бросает."""
    from uk_management_bot.services.notification_service import (
        _get_shared_bot, send_to_user,
    )

    sent = 0
    for chat_id, text in messages:
        try:
            if await send_to_user(bot or _get_shared_bot(), chat_id, text):
                sent += 1
        except Exception as e:
            logger.warning("Notify-сообщение получателю %s не отправлено: %s", chat_id, e)
    return sent


def render_channel_status_text(
    request: Optional[Request], old_status: str, new_status: str
) -> Optional[str]:
    """Render-фаза канальной ленты (для сборки в worker-потоке при живом request)."""
    if request is None:
        return None
    from uk_management_bot.services.notification_service import (
        _build_request_status_message_channel,
    )
    return _build_request_status_message_channel(request, old_status, new_status)


async def send_channel_status_text(bot, text: Optional[str], request_number: str = "?") -> None:
    """Send-фаза канальной ленты. Best-effort, не бросает (зеркало
    ``notify_channel_status_changed``, но без сессии/ORM в async-части)."""
    if text is None:
        return
    from uk_management_bot.services.notification_service import send_to_channel

    try:
        await send_to_channel(bot, text)
    except Exception as e:
        logger.warning(
            "Канальное уведомление по заявке %s не отправлено: %s", request_number, e,
        )


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
