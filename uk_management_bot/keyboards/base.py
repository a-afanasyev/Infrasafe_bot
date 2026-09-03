import logging

from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from uk_management_bot.utils.helpers import get_text
from uk_management_bot.utils.callback_factories import RoleSwitchCB, RatingCB
from uk_management_bot.config.settings import settings

logger = logging.getLogger(__name__)

# Роль-капабилити «полевой контролёр» (ввод показаний в «Учёт ресурсов»). Даёт
# web_app-кнопку Mini App, но НЕ участвует в переключении active_role.
METER_ENTRY_ROLE = "resource_meter_entry"

def get_main_keyboard(language: str = "ru") -> ReplyKeyboardMarkup:
    """Главная клавиатура (вариант по умолчанию для обратной совместимости).

    Используется старым кодом. Не учитывает роли.
    """
    return get_main_keyboard_for_role(active_role="applicant", roles=["applicant"], language=language)


def get_contextual_keyboard(roles: list = None, active_role: str = None, language: str = "ru") -> ReplyKeyboardMarkup:
    """Получить клавиатуру с учетом текущих ролей пользователя.

    Если роли не переданы, возвращает базовую клавиатуру.
    """
    if not roles or not active_role:
        return get_main_keyboard(language=language)
    return get_main_keyboard_for_role(active_role=active_role, roles=roles, language=language)


def _load_keyboard_context(db, user_id: int):
    """DB-юнит клавиатуры (AUD3-37 F2): исполняется в worker-потоке run_db.

    Возвращает DTO ``(roles, active_role, user_status, language)`` или None,
    если пользователя нет (легитимный случай, не ошибка).
    """
    from uk_management_bot.database.models.user import User
    from uk_management_bot.utils.auth_helpers import get_user_roles

    user = db.query(User).filter(User.telegram_id == user_id).first()
    if not user:
        return None

    roles = get_user_roles(user)
    return (
        roles,
        user.active_role or (roles[0] if roles else "applicant"),
        user.status or "approved",
        user.language or "ru",
    )


async def get_user_contextual_keyboard(user_id: int, *, _db=None) -> ReplyKeyboardMarkup:
    """Получить клавиатуру пользователя, загрузив его роли из БД.

    AUD3-37 (F2): DB-фаза — юнит ``_load_keyboard_context`` в worker-потоке
    через ``run_db`` со своей короткой сессией (раньше здесь была собственная
    ``SessionLocal()`` прямо на event loop — третья сессия update и loop-блок
    на ~40 колл-сайтах). Тестовый seam — keyword-only ``_db``.

    Пользователя нет в БД — легитимный случай (незарегистрированный), отдаём
    базовую клавиатуру. Любой ДРУГОЙ сбой логируется и пробрасывается.

    AUD5-CODE-7: раньше здесь стоял `except Exception: return get_main_keyboard()`
    без логирования, и это давало два эффекта разом. Во-первых, сбой БД был
    невидим: ни строки в логах. Во-вторых — и это хуже — менеджер в момент сбоя
    получал applicant-клавиатуру, а reply-клавиатура в Telegram ЛИПКАЯ: она
    остаётся у пользователя, пока её не заменит следующий ответ бота. То есть
    секундный блип БД оставлял человека с чужим меню надолго после того, как БД
    выздоровела, и выглядело это как потеря прав.

    Проброс безопасен и даёт лучший исход: глобальный хендлер (`main.py:300`)
    пишет ERROR со трейсбеком, отправляет пользователю `errors.unexpected` и
    возвращает True — процесс не падает, а человек видит понятную ошибку и
    повторяет действие вместо того, чтобы застрять с неверным меню.
    """
    from uk_management_bot.database.session import run_db

    try:
        ctx = await run_db(lambda s: _load_keyboard_context(s, user_id), db=_db)

        if ctx is not None:
            roles, active_role, user_status, language = ctx
            return get_main_keyboard_for_role(
                active_role=active_role,
                roles=roles,
                user_status=user_status,
                language=language
            )

        # Незарегистрированный пользователь — не ошибка, ролей просто нет.
        logger.debug("Клавиатура по умолчанию: пользователь %s не найден в БД", user_id)
        return get_main_keyboard()

    except Exception:
        logger.error(
            "Не удалось построить клавиатуру по ролям для пользователя %s — "
            "проброс вместо подмены applicant-клавиатурой (AUD5-CODE-7)",
            user_id, exc_info=True,
        )
        raise

def get_cancel_keyboard(language: str = "ru") -> ReplyKeyboardMarkup:
    """Клавиатура с кнопкой отмены"""
    builder = ReplyKeyboardBuilder()
    builder.add(KeyboardButton(text=get_text("buttons.cancel", language=language)))
    return builder.as_markup(resize_keyboard=True)

def get_yes_no_keyboard(language: str = "ru") -> ReplyKeyboardMarkup:
    """Клавиатура Да/Нет"""
    builder = ReplyKeyboardBuilder()
    builder.add(KeyboardButton(text=get_text("buttons.yes", language=language)))
    builder.add(KeyboardButton(text=get_text("buttons.no", language=language)))
    builder.add(KeyboardButton(text=get_text("buttons.back", language=language)))
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)

def get_rating_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для оценки (1-5 звезд)"""
    builder = InlineKeyboardBuilder()

    for i in range(1, 6):
        builder.add(InlineKeyboardButton(
            text=f"{'⭐' * i}",
            callback_data=RatingCB(score=i).pack()
        ))

    builder.adjust(5)
    return builder.as_markup()


def get_main_keyboard_for_role(
    active_role: str,
    roles: list[str],
    user_status: str = None,
    language: str = "ru"
) -> ReplyKeyboardMarkup:
    """Главная клавиатура с учётом активной роли и доступных ролей.

    Сценарии:
    - applicant: стандартные кнопки (создать/мои заявки, профиль, помощь)
    - executor: кнопки смены и заявок исполнителя
    - manager: добавляются админ‑кнопки
    - pending: только базовые кнопки без создания заявок
    """
    builder = ReplyKeyboardBuilder()

    unique_roles: list[str] = []
    if roles:
        for r in roles:
            if isinstance(r, str) and r not in unique_roles:
                unique_roles.append(r)

    if active_role == "executor":
        # Клавиатура исполнителя
        builder.add(KeyboardButton(text=get_text("main_menu.active_requests", language=language)))
        # FEAT-группы: пул «свободных» group-заявок (взять из общего пула)
        builder.add(KeyboardButton(text=get_text("main_menu.group_pool", language=language)))
        builder.add(KeyboardButton(text=get_text("main_menu.archive", language=language)))
        builder.add(KeyboardButton(text=get_text("main_menu.profile", language=language)))
        builder.add(KeyboardButton(text=get_text("main_menu.help", language=language)))
        # Быстрый доступ к сменам отдельной кнопкой
        builder.add(KeyboardButton(text=get_text("main_menu.shift", language=language)))
        builder.add(KeyboardButton(text=get_text("main_menu.my_shifts", language=language)))
    elif active_role == "inspector":
        # Клавиатура обходчика: одноцелевая роль — завести заявку с обхода
        # (двор→дом, building-level). Создание доступно только approved-обходчику.
        if user_status != "pending":
            builder.add(KeyboardButton(text=get_text("main_menu.inspector_create", language=language)))
        builder.add(KeyboardButton(text=get_text("main_menu.profile", language=language)))
        builder.add(KeyboardButton(text=get_text("main_menu.help", language=language)))
    else:
        # Базовые кнопки для заявителя/других ролей
        # Кнопку "Создать заявку" (applicant-flow) НЕ показываем:
        #  - пользователям на модерации (pending);
        #  - менеджеру/админу (applicant-flow стал role-gated; менеджер заводит
        #    заявки через call-центр/дашборд — план «Обходчик»).
        if user_status != "pending" and active_role not in ("manager", "admin"):
            builder.add(KeyboardButton(text=get_text("main_menu.create_request", language=language)))
        builder.add(KeyboardButton(text=get_text("main_menu.my_requests", language=language)))
        builder.add(KeyboardButton(text=get_text("main_menu.acceptance", language=language)))  # Кнопка для приёмки выполненных заявок
        # Контроль доступа (ANPR/шлагбаум, ТЗ §6.4) — личный кабинет жителя.
        # Только approved-applicant: pending ещё не подтверждён, менеджер/админ
        # ведут доступ через дашборд.
        if user_status != "pending" and active_role == "applicant":
            builder.add(KeyboardButton(text=get_text("main_menu.access_control", language=language)))
        builder.add(KeyboardButton(text=get_text("main_menu.profile", language=language)))
        builder.add(KeyboardButton(text=get_text("main_menu.help", language=language)))

    # Ввод показаний (Mini App «Учёт ресурсов») — капабилити-роль контролёра,
    # показываем по факту наличия роли, независимо от active_role. Кнопка
    # текстовая, БЕЗ web_app (reply web_app не передаёт initData) — ссылку
    # шлёт handlers/webapp_buttons.py inline-кнопкой по нажатию.
    if METER_ENTRY_ROLE in unique_roles and settings.FRONTEND_URL:
        builder.add(KeyboardButton(text=get_text("base.handlers.btn_meter_entry", language=language)))

    # Обратная связь — доступна всем авторизованным ролям
    builder.add(KeyboardButton(text=get_text("main_menu.feedback", language=language)))

    # Кнопка выбор роли при наличии ≥2 переключаемых ролей (капабилити
    # resource_meter_entry не переключается — не считаем её).
    switchable_roles = [r for r in unique_roles if r != METER_ENTRY_ROLE]
    if len(switchable_roles) > 1:
        builder.add(KeyboardButton(text=get_text("main_menu.switch_role", language=language)))

    # Кнопки менеджера (только для активных ролей admin/manager)
    if active_role in ["admin", "manager"]:
        builder.add(KeyboardButton(text=get_text("main_menu.admin_panel", language=language)))

    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)


def get_role_switch_inline(roles: list[str], active_role: str, language: str = "ru") -> InlineKeyboardMarkup:
    """Inline‑клавиатура для переключения роли.

    - Показывает только роли, которые есть у пользователя
    - Активная роль помечается галочкой
    """
    builder = InlineKeyboardBuilder()

    for role in roles or []:
        if role == METER_ENTRY_ROLE:
            continue  # капабилити, не переключаемая роль
        name = get_text(f"roles.{role}", language=language)
        mark = " ✓" if role == active_role else ""
        builder.add(InlineKeyboardButton(
            text=f"{name}{mark}",
            callback_data=RoleSwitchCB(target=role).pack()
        ))

    builder.adjust(3)
    return builder.as_markup()


def get_start_role_choice_inline(language: str = "ru") -> InlineKeyboardMarkup:
    """Inline-клавиатура развилки первого входа: житель или сотрудник.

    Инлайн, а не reply: reply-клавиатура «липкая» — проигнорированная, она
    висела бы поверх следующих экранов, а инлайн-разметку снимает сам хендлер.
    """
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(
        text=get_text("start_role.btn_resident", language=language),
        callback_data="start_role:resident",
    ))
    builder.add(InlineKeyboardButton(
        text=get_text("start_role.btn_employee", language=language),
        callback_data="start_role:employee",
    ))
    builder.adjust(1)
    return builder.as_markup()


def get_no_invite_token_inline(language: str = "ru") -> InlineKeyboardMarkup:
    """Выход из шага ввода токена: «у меня нет кода» → вернуться к жителю."""
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(
        text=get_text("start_role.btn_no_token", language=language),
        callback_data="start_role:no_token",
    ))
    return builder.as_markup()


def get_executor_suggestion_inline(yes_text: str, no_text: str) -> InlineKeyboardMarkup:
    """Inline‑клавиатура для предложения перейти в режим исполнителя после старта смены.

    Параметры:
    - yes_text: Подпись кнопки согласия (локализованный текст)
    - no_text: Подпись кнопки отказа (локализованный текст)

    Возвращает InlineKeyboardMarkup с двумя кнопками:
    - Перейти в режим сотрудника → RoleSwitchCB(target="executor")
    - Остаться в текущем режиме → callback_data "suggest_executor_skip"
    """
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text=yes_text, callback_data=RoleSwitchCB(target="executor").pack()))
    builder.add(InlineKeyboardButton(text=no_text, callback_data="suggest_executor_skip"))
    builder.adjust(1)
    return builder.as_markup()
