from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder

def get_main_keyboard() -> ReplyKeyboardMarkup:
    """Главная клавиатура (вариант по умолчанию для обратной совместимости).

    Используется старым кодом. Не учитывает роли.
    """
    return get_main_keyboard_for_role(active_role="applicant", roles=["applicant"])


def get_contextual_keyboard(roles: list = None, active_role: str = None) -> ReplyKeyboardMarkup:
    """Получить клавиатуру с учетом текущих ролей пользователя.
    
    Если роли не переданы, возвращает базовую клавиатуру.
    """
    if not roles or not active_role:
        return get_main_keyboard()
    return get_main_keyboard_for_role(active_role=active_role, roles=roles)


def get_user_contextual_keyboard(user_id: int) -> ReplyKeyboardMarkup:
    """Получить клавиатуру пользователя, загрузив его роли из БД.
    
    Если роли не найдены, возвращает базовую клавиатуру.
    """
    try:
        from database.session import SessionLocal
        from database.models.user import User
        import json
        
        db = SessionLocal()
        user = db.query(User).filter(User.telegram_id == user_id).first()
        
        if user and user.roles:
            roles = json.loads(user.roles)
            active_role = user.active_role or (roles[0] if roles else "applicant")
            db.close()
            return get_main_keyboard_for_role(active_role=active_role, roles=roles)
        
        db.close()
        return get_main_keyboard()
        
    except Exception:
        return get_main_keyboard() 

def get_cancel_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура с кнопкой отмены"""
    builder = ReplyKeyboardBuilder()
    builder.add(KeyboardButton(text="❌ Отмена"))
    return builder.as_markup(resize_keyboard=True)

def get_yes_no_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура Да/Нет"""
    builder = ReplyKeyboardBuilder()
    builder.add(KeyboardButton(text="✅ Да"))
    builder.add(KeyboardButton(text="❌ Нет"))
    builder.add(KeyboardButton(text="🔙 Назад"))
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)

def get_rating_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для оценки (1-5 звезд)"""
    builder = InlineKeyboardBuilder()
    
    for i in range(1, 6):
        builder.add(InlineKeyboardButton(
            text=f"{'⭐' * i}",
            callback_data=f"rate_{i}"
        ))
    
    builder.adjust(5)
    return builder.as_markup()


def get_main_keyboard_for_role(active_role: str, roles: list[str], user_status: str = None) -> ReplyKeyboardMarkup:
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
        builder.add(KeyboardButton(text="🛠 Активные заявки"))
        builder.add(KeyboardButton(text="📦 Архив"))
        builder.add(KeyboardButton(text="👤 Профиль"))
        builder.add(KeyboardButton(text="ℹ️ Помощь"))
        # Быстрый доступ к сменам отдельной кнопкой
        builder.add(KeyboardButton(text="🔄 Смена"))
    else:
        # Базовые кнопки для заявителя/других ролей
        # Не показываем кнопку "Создать заявку" для пользователей на модерации
        if user_status != "pending":
            builder.add(KeyboardButton(text="📝 Создать заявку"))
        builder.add(KeyboardButton(text="📋 Мои заявки"))
        builder.add(KeyboardButton(text="👤 Профиль"))
        builder.add(KeyboardButton(text="ℹ️ Помощь"))

    # Кнопка выбор роли при наличии ≥2 ролей
    if len(unique_roles) > 1:
        builder.add(KeyboardButton(text="🔀 Выбрать роль"))

    # Кнопки менеджера (только для активных ролей admin/manager)
    if active_role in ["admin", "manager"]:
        builder.add(KeyboardButton(text="🔧 Админ панель"))
        builder.add(KeyboardButton(text="📊 Статистика"))

    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)


def get_role_switch_inline(roles: list[str], active_role: str) -> InlineKeyboardMarkup:
    """Inline‑клавиатура для переключения роли.

    - Показывает только роли, которые есть у пользователя
    - Активная роль помечается галочкой
    """
    builder = InlineKeyboardBuilder()
    role_names = {
        "applicant": "Житель",
        "executor": "Сотрудник",
        "manager": "Менеджер",
        "admin": "Администратор",
    }

    for role in roles or []:
        name = role_names.get(role, role)
        mark = " ✓" if role == active_role else ""
        builder.add(InlineKeyboardButton(text=f"{name}{mark}", callback_data=f"switch_role:{role}"))

    builder.adjust(3)
    return builder.as_markup()


def get_executor_suggestion_inline(yes_text: str, no_text: str) -> InlineKeyboardMarkup:
    """Inline‑клавиатура для предложения перейти в режим исполнителя после старта смены.

    Параметры:
    - yes_text: Подпись кнопки согласия (локализованный текст)
    - no_text: Подпись кнопки отказа (локализованный текст)

    Возвращает InlineKeyboardMarkup с двумя кнопками:
    - Перейти в режим сотрудника → callback_data "switch_role:executor"
    - Остаться в текущем режиме → callback_data "suggest_executor_skip"
    """
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text=yes_text, callback_data="switch_role:executor"))
    builder.add(InlineKeyboardButton(text=no_text, callback_data="suggest_executor_skip"))
    builder.adjust(1)
    return builder.as_markup()
