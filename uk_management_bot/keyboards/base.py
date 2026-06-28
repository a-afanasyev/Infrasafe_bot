from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from uk_management_bot.utils.helpers import get_text
from uk_management_bot.utils.callback_factories import RoleSwitchCB, RatingCB

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


def get_user_contextual_keyboard(user_id: int) -> ReplyKeyboardMarkup:
    """Получить клавиатуру пользователя, загрузив его роли из БД.

    Если роли не найдены, возвращает базовую клавиатуру.
    """
    from uk_management_bot.database.session import SessionLocal
    from uk_management_bot.database.models.user import User

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.telegram_id == user_id).first()

        if user:
            from uk_management_bot.utils.auth_helpers import get_user_roles

            roles = get_user_roles(user)

            active_role = user.active_role or (roles[0] if roles else "applicant")
            user_status = user.status or "approved"
            language = user.language or "ru"

            return get_main_keyboard_for_role(
                active_role=active_role,
                roles=roles,
                user_status=user_status,
                language=language
            )

        return get_main_keyboard()

    except Exception:
        return get_main_keyboard()
    finally:
        db.close()

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

    # Обратная связь — доступна всем авторизованным ролям
    builder.add(KeyboardButton(text=get_text("main_menu.feedback", language=language)))

    # Кнопка выбор роли при наличии ≥2 ролей
    if len(unique_roles) > 1:
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
        name = get_text(f"roles.{role}", language=language)
        mark = " ✓" if role == active_role else ""
        builder.add(InlineKeyboardButton(
            text=f"{name}{mark}",
            callback_data=RoleSwitchCB(target=role).pack()
        ))

    builder.adjust(3)
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
