"""
Клавиатуры для системы верификации пользователей

Содержит inline-клавиатуры для:
- Главного меню верификации
- Управления верификацией пользователей
- Проверки документов
- Управления правами доступа
"""

from typing import Dict, List
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from uk_management_bot.utils.helpers import get_text
from uk_management_bot.database.models.user_verification import DocumentType


def get_verification_main_keyboard(stats: Dict[str, int], language: str = 'ru') -> InlineKeyboardMarkup:
    """
    Главное меню панели верификации
    
    Args:
        stats: Статистика верификации
        language: Язык интерфейса
        
    Returns:
        InlineKeyboardMarkup с главным меню
    """
    buttons = [
        # Статистика
        [InlineKeyboardButton(
            text=f"📊 {get_text('verification.stats', language)}",
            callback_data="verification_stats"
        )],
        
        # Списки пользователей с счетчиками
        [InlineKeyboardButton(
            text=f"⏳ {get_text('verification.pending_users', language)} ({stats.get('pending', 0)})",
            callback_data="verification_list_pending_1"
        )],
        [InlineKeyboardButton(
            text=f"✅ {get_text('verification.verified_users', language)} ({stats.get('verified', 0)})",
            callback_data="verification_list_verified_1"
        )],
        [InlineKeyboardButton(
            text=f"❌ {get_text('verification.rejected_users', language)} ({stats.get('rejected', 0)})",
            callback_data="verification_list_rejected_1"
        )],
        
        # Документы
        [InlineKeyboardButton(
            text=f"📄 {get_text('verification.pending_documents', language)} ({stats.get('pending_documents', 0)})",
            callback_data="verification_documents_pending_1"
        )],
        
        # Назад
        [InlineKeyboardButton(
            text=f"◀️ {get_text('buttons.back', language)}",
            callback_data="user_management_panel"
        )]
    ]
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_user_verification_keyboard(user_id: int, language: str = 'ru') -> InlineKeyboardMarkup:
    """
    Клавиатура управления верификацией пользователя
    
    Args:
        user_id: ID пользователя
        language: Язык интерфейса
        
    Returns:
        InlineKeyboardMarkup с действиями
    """
    buttons = [
        # Действия верификации
        [InlineKeyboardButton(
            text=f"✅ {get_text('verification.approve_user', language)}",
            callback_data=f"verify_approve_{user_id}"
        )],
        [InlineKeyboardButton(
            text=f"❌ {get_text('verification.reject_user', language)}",
            callback_data=f"verify_reject_{user_id}"
        )],
        
        # Запрос дополнительной информации
        [InlineKeyboardButton(
            text=f"📝 {get_text('verification.request_info', language)}",
            callback_data=f"verification_request_{user_id}"
        )],
        
        # Управление правами доступа
        [InlineKeyboardButton(
            text=f"🔑 {get_text('verification.access_rights', language)}",
            callback_data=f"access_rights_{user_id}"
        )],
        
        # Документы
        [InlineKeyboardButton(
            text=f"📄 {get_text('verification.view_documents', language)}",
            callback_data=f"view_user_documents_{user_id}"
        )],
        
        # Назад
        [InlineKeyboardButton(
            text=f"◀️ {get_text('buttons.back', language)}",
            callback_data="user_verification_panel"
        )]
    ]
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_verification_request_keyboard(user_id: int, language: str = 'ru') -> InlineKeyboardMarkup:
    """
    Клавиатура запроса дополнительной информации
    
    Args:
        user_id: ID пользователя
        language: Язык интерфейса
        
    Returns:
        InlineKeyboardMarkup с типами запросов
    """
    buttons = [
        # Типы запрашиваемой информации
        [InlineKeyboardButton(
            text=f"📍 {get_text('verification.request_address', language)}",
            callback_data=f"request_info_{user_id}_address"
        )],
        [InlineKeyboardButton(
            text=f"📄 {get_text('verification.request_passport', language)}",
            callback_data=f"request_info_{user_id}_passport"
        )],
        [InlineKeyboardButton(
            text=f"🏠 {get_text('verification.request_property_deed', language)}",
            callback_data=f"request_info_{user_id}_property_deed"
        )],
        [InlineKeyboardButton(
            text=f"📋 {get_text('verification.request_rental_agreement', language)}",
            callback_data=f"request_info_{user_id}_rental_agreement"
        )],
        [InlineKeyboardButton(
            text=f"💡 {get_text('verification.request_utility_bill', language)}",
            callback_data=f"request_info_{user_id}_utility_bill"
        )],
        [InlineKeyboardButton(
            text=f"📝 {get_text('verification.request_other', language)}",
            callback_data=f"request_info_{user_id}_other"
        )],
        
        # Назад
        [InlineKeyboardButton(
            text=f"◀️ {get_text('buttons.back', language)}",
            callback_data=f"verification_user_{user_id}"
        )]
    ]
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_document_verification_keyboard(document_id: int, language: str = 'ru') -> InlineKeyboardMarkup:
    """
    Клавиатура проверки документа
    
    Args:
        document_id: ID документа
        language: Язык интерфейса
        
    Returns:
        InlineKeyboardMarkup с действиями
    """
    buttons = [
        # Действия с документом
        [InlineKeyboardButton(
            text=f"✅ {get_text('verification.approve_document', language)}",
            callback_data=f"document_approve_{document_id}"
        )],
        [InlineKeyboardButton(
            text=f"❌ {get_text('verification.reject_document', language)}",
            callback_data=f"document_reject_{document_id}"
        )],
        [InlineKeyboardButton(
            text=f"📥 Скачать документ",
            callback_data=f"download_document_{document_id}"
        )],
        
        # Назад
        [InlineKeyboardButton(
            text=f"◀️ {get_text('buttons.back', language)}",
            callback_data="verification_user_documents"
        )]
    ]
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_document_management_keyboard(user_id: int, language: str = 'ru') -> InlineKeyboardMarkup:
    """
    Клавиатура управления документами пользователя
    
    Args:
        user_id: ID пользователя
        language: Язык интерфейса
        
    Returns:
        InlineKeyboardMarkup с действиями
    """
    buttons = [
        # Действия с документами
        [InlineKeyboardButton(
            text=f"📝 Запросить дополнительные документы",
            callback_data=f"request_documents_{user_id}"
        )],
        
        # Назад
        [InlineKeyboardButton(
            text=f"◀️ {get_text('buttons.back', language)}",
            callback_data=f"user_mgmt_user_{user_id}"
        )]
    ]
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_access_rights_keyboard(user_id: int, language: str = 'ru') -> InlineKeyboardMarkup:
    """
    Клавиатура управления правами доступа
    
    Args:
        user_id: ID пользователя
        language: Язык интерфейса
        
    Returns:
        InlineKeyboardMarkup с действиями
    """
    buttons = [
        # Предоставление прав доступа
        [InlineKeyboardButton(
            text=f"🏠 {get_text('verification.grant_apartment', language)}",
            callback_data=f"grant_access_{user_id}_apartment"
        )],
        [InlineKeyboardButton(
            text=f"🏢 {get_text('verification.grant_house', language)}",
            callback_data=f"grant_access_{user_id}_house"
        )],
        [InlineKeyboardButton(
            text=f"🏘️ {get_text('verification.grant_yard', language)}",
            callback_data=f"grant_access_{user_id}_yard"
        )],
        
        # Отзыв прав доступа
        [InlineKeyboardButton(
            text=f"🚫 {get_text('verification.revoke_rights', language)}",
            callback_data=f"revoke_rights_{user_id}"
        )],
        
        # Назад
        [InlineKeyboardButton(
            text=f"◀️ {get_text('buttons.back', language)}",
            callback_data=f"verification_user_{user_id}"
        )]
    ]
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_verification_list_keyboard(users_data: Dict, list_type: str, language: str = 'ru') -> InlineKeyboardMarkup:
    """
    Клавиатура списка пользователей для верификации
    
    Args:
        users_data: Данные пользователей с пагинацией
        list_type: Тип списка (pending, verified, rejected)
        language: Язык интерфейса
        
    Returns:
        InlineKeyboardMarkup со списком пользователей
    """
    buttons = []
    
    # Пользователи (по 5 на страницу для удобства)
    for user in users_data.get('users', []):
        user_name = _format_user_name(user)
        status_emoji = _get_verification_status_emoji(user.verification_status)
        
        buttons.append([InlineKeyboardButton(
            text=f"{status_emoji} {user_name}",
            callback_data=f"verification_user_{user.id}"
        )])
    
    # Если пользователей нет
    if not users_data.get('users'):
        buttons.append([InlineKeyboardButton(
            text=get_text('verification.no_users_found', language),
            callback_data="no_action"
        )])
    
    # Пагинация
    pagination_buttons = []
    current_page = users_data.get('current_page', 1)
    total_pages = users_data.get('total_pages', 1)
    
    if current_page > 1:
        pagination_buttons.append(InlineKeyboardButton(
            text="◀️",
            callback_data=f"verification_list_{list_type}_{current_page - 1}"
        ))
    
    pagination_buttons.append(InlineKeyboardButton(
        text=f"{current_page}/{total_pages}",
        callback_data="no_action"
    ))
    
    if current_page < total_pages:
        pagination_buttons.append(InlineKeyboardButton(
            text="▶️",
            callback_data=f"verification_list_{list_type}_{current_page + 1}"
        ))
    
    if pagination_buttons:
        buttons.append(pagination_buttons)
    
    # Назад
    buttons.append([InlineKeyboardButton(
        text=f"◀️ {get_text('buttons.back', language)}",
        callback_data="user_verification_panel"
    )])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_documents_list_keyboard(documents_data: Dict, language: str = 'ru') -> InlineKeyboardMarkup:
    """
    Клавиатура списка документов для проверки
    
    Args:
        documents_data: Данные документов с пагинацией
        language: Язык интерфейса
        
    Returns:
        InlineKeyboardMarkup со списком документов
    """
    buttons = []
    
    # Документы (по 5 на страницу для удобства)
    for document in documents_data.get('documents', []):
        document_name = f"{document.document_type.value}"
        status_emoji = _get_document_status_emoji(document.verification_status)
        
        buttons.append([InlineKeyboardButton(
            text=f"{status_emoji} {document_name}",
            callback_data=f"document_verify_{document.id}"
        )])
    
    # Если документов нет
    if not documents_data.get('documents'):
        buttons.append([InlineKeyboardButton(
            text=get_text('verification.no_documents_found', language),
            callback_data="no_action"
        )])
    
    # Пагинация
    pagination_buttons = []
    current_page = documents_data.get('current_page', 1)
    total_pages = documents_data.get('total_pages', 1)
    
    if current_page > 1:
        pagination_buttons.append(InlineKeyboardButton(
            text="◀️",
            callback_data=f"verification_documents_pending_{current_page - 1}"
        ))
    
    pagination_buttons.append(InlineKeyboardButton(
        text=f"{current_page}/{total_pages}",
        callback_data="no_action"
    ))
    
    if current_page < total_pages:
        pagination_buttons.append(InlineKeyboardButton(
            text="▶️",
            callback_data=f"verification_documents_pending_{current_page + 1}"
        ))
    
    if pagination_buttons:
        buttons.append(pagination_buttons)
    
    # Назад
    buttons.append([InlineKeyboardButton(
        text=f"◀️ {get_text('buttons.back', language)}",
        callback_data="user_verification_panel"
    )])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_cancel_keyboard(language: str = 'ru') -> InlineKeyboardMarkup:
    """
    Клавиатура отмены действия
    
    Args:
        language: Язык интерфейса
        
    Returns:
        InlineKeyboardMarkup с кнопкой отмены
    """
    buttons = [
        [InlineKeyboardButton(
            text=f"❌ {get_text('buttons.cancel', language)}",
            callback_data="cancel_action"
        )]
    ]
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ═══ ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ═══

def _format_user_name(user) -> str:
    """Форматировать имя пользователя для отображения"""
    if user.first_name and user.last_name:
        return f"{user.first_name} {user.last_name}"
    elif user.first_name:
        return user.first_name
    elif user.username:
        return f"@{user.username}"
    else:
        return f"User {user.id}"


def _get_verification_status_emoji(status: str) -> str:
    """Получить эмодзи для статуса верификации"""
    status_emojis = {
        'pending': '⏳',
        'verified': '✅',
        'rejected': '❌',
        'requested': '📝'
    }
    return status_emojis.get(status, '❓')


def _get_document_status_emoji(status) -> str:
    """Получить эмодзи для статуса документа"""
    status_emojis = {
        'pending': '⏳',
        'approved': '✅',
        'rejected': '❌'
    }
    return status_emojis.get(status.value, '❓')


def get_document_request_keyboard(user_id: int, language: str = 'ru') -> InlineKeyboardMarkup:
    """
    Клавиатура выбора типа документа для запроса
    
    Args:
        user_id: ID пользователя
        language: Язык интерфейса
        
    Returns:
        InlineKeyboardMarkup с типами документов
    """
    buttons = []
    
    # Типы документов
    document_types = [
        (DocumentType.PASSPORT, "passport"),
        (DocumentType.PROPERTY_DEED, "property_deed"),
        (DocumentType.RENTAL_AGREEMENT, "rental_agreement"),
        (DocumentType.UTILITY_BILL, "utility_bill"),
        (DocumentType.OTHER, "other")
    ]
    
    # Группируем по 2 в ряд
    for i in range(0, len(document_types), 2):
        row = []
        
        for j in range(2):
            if i + j < len(document_types):
                doc_type, key = document_types[i + j]
                doc_name = get_text(f"verification.document_types.{key}", language)
                
                row.append(InlineKeyboardButton(
                    text=f"📄 {doc_name}",
                    callback_data=f"request_document_{user_id}_{doc_type.value}"
                ))
        
        buttons.append(row)
    
    # Назад
    buttons.append([InlineKeyboardButton(
        text=f"◀️ {get_text('buttons.back', language)}",
        callback_data=f"back_to_user_details_{user_id}"
    )])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_document_checklist_keyboard(user_id: int, selected_docs: list = None, language: str = 'ru') -> InlineKeyboardMarkup:
    """
    Клавиатура с галочками для выбора документов
    
    Args:
        user_id: ID пользователя
        selected_docs: Список уже выбранных документов
        language: Язык интерфейса
        
    Returns:
        InlineKeyboardMarkup с галочками
    """
    if selected_docs is None:
        selected_docs = []
    
    buttons = []
    
    # Типы документов с галочками
    document_types = [
        (DocumentType.PASSPORT, "passport"),
        (DocumentType.PROPERTY_DEED, "property_deed"),
        (DocumentType.RENTAL_AGREEMENT, "rental_agreement"),
        (DocumentType.UTILITY_BILL, "utility_bill"),
        (DocumentType.OTHER, "other")
    ]
    
    # Создаем кнопки с галочками
    for doc_type, key in document_types:
        doc_name = get_text(f"verification.document_types.{key}", language)
        
        # Логируем для отладки локализации
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"🔍 DOCUMENT_CHECKLIST: key={key}, doc_name={doc_name}, language={language}")
        
        # Проверяем, выбран ли документ
        if doc_type.value in selected_docs:
            text = f"✅ {doc_name}"
            callback_data = f"uncheck_document_{user_id}_{doc_type.value}"
        else:
            text = f"⬜️ {doc_name}"
            callback_data = f"check_document_{user_id}_{doc_type.value}"
        
        buttons.append([InlineKeyboardButton(
            text=text,
            callback_data=callback_data
        )])
    
    # Кнопки действий
    action_buttons = []
    
    if selected_docs:
        # Ограничиваем длину callback_data (максимум 64 символа)
        docs_str = ','.join(selected_docs[:3])  # Берем только первые 3 документа
        if len(selected_docs) > 3:
            docs_str += f"+{len(selected_docs)-3}"  # Показываем количество остальных
        
        action_buttons.append(InlineKeyboardButton(
            text=f"📤 {get_text('verification.request_selected_documents', language)}",
            callback_data=f"req_docs_{user_id}_{docs_str}"
        ))
    
    action_buttons.append(InlineKeyboardButton(
        text=f"❌ {get_text('buttons.cancel', language)}",
        callback_data=f"cancel_document_selection_{user_id}"
    ))
    
    if action_buttons:
        buttons.append(action_buttons)
    
    # Назад
    buttons.append([InlineKeyboardButton(
        text=f"◀️ {get_text('buttons.back', language)}",
        callback_data=f"back_to_user_details_{user_id}"
    )])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)
