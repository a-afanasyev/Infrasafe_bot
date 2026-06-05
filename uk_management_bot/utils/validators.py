import re
from typing import Optional, Tuple, List
from uk_management_bot.utils.constants import (
    MAX_ADDRESS_LENGTH, MAX_DESCRIPTION_LENGTH, MAX_APARTMENT_LENGTH,
    MAX_PHOTO_SIZE, MAX_VIDEO_SIZE, MAX_DOCUMENT_SIZE,
    REQUEST_CATEGORIES, REQUEST_STATUSES, USER_ROLES
)

class Validator:
    """Класс для валидации данных"""
    
    @staticmethod
    def validate_phone(phone: str, language: str = "ru") -> Tuple[bool, str]:
        """
        Валидация номера телефона
        
        Args:
            phone: Номер телефона для валидации
            language: Язык для сообщений об ошибках (ru/uz)
            
        Returns:
            Tuple[bool, str]: (валиден ли номер, сообщение)
        """
        from uk_management_bot.utils.helpers import get_text
        
        if not phone:
            from uk_management_bot.utils.safe_localization import safe_get_text
            error_msg = get_text("validation.phone_empty", language=language)
            if error_msg == "validation.phone_empty":  # Fallback если ключ не найден
                error_msg = safe_get_text("errors.phone_empty", language=language, default="Номер телефона не может быть пустым")
            return False, error_msg
        
        # Очищаем номер от пробелов и символов
        clean_phone = re.sub(r'[\s\-\(\)]', '', phone)
        
        # Проверяем узбекские номера
        patterns = [
            r'^\+998[0-9]{9}$',  # +998XXXXXXXXX
            r'^998[0-9]{9}$',    # 998XXXXXXXXX
            r'^[0-9]{9}$'        # XXXXXXXXX
        ]
        
        for pattern in patterns:
            if re.match(pattern, clean_phone):
                success_msg = get_text("validation.phone_valid", language=language)
                if success_msg == "validation.phone_valid":  # Fallback если ключ не найден
                    success_msg = safe_get_text("errors.phone_valid", language=language, default="Номер телефона корректен")
                return True, success_msg
        
        error_msg = get_text("validation.phone_invalid_format", language=language)
        if error_msg == "validation.phone_invalid_format":  # Fallback если ключ не найден
            error_msg = safe_get_text("errors.phone_invalid_format", language=language, default="Неверный формат номера телефона")
        return False, error_msg
    
    @staticmethod
    def validate_description(description: str, language: str = "ru") -> Tuple[bool, str]:
        """
        Валидация описания
        
        Args:
            description: Описание для валидации
            language: Язык для сообщений об ошибках (ru/uz)
            
        Returns:
            Tuple[bool, str]: (валидно ли описание, сообщение)
        """
        from uk_management_bot.utils.helpers import get_text
        
        if not description:
            error_msg = get_text("validation.description_empty", language=language)
            if error_msg == "validation.description_empty":  # Fallback если ключ не найден
                error_msg = "Описание не может быть пустым"
            return False, error_msg
        
        if len(description.strip()) < 10:
            error_msg = get_text("validation.description_too_short", language=language, min_length=10)
            if error_msg == "validation.description_too_short":  # Fallback если ключ не найден
                error_msg = "Описание должно содержать минимум 10 символов"
            else:
                try:
                    error_msg = error_msg.format(min_length=10)
                except (KeyError, ValueError):
                    error_msg = f"Описание должно содержать минимум 10 символов"
            return False, error_msg
        
        if len(description) > MAX_DESCRIPTION_LENGTH:
            error_msg = get_text("validation.description_too_long", language=language, max_length=MAX_DESCRIPTION_LENGTH)
            if error_msg == "validation.description_too_long":  # Fallback если ключ не найден
                error_msg = f"Описание слишком длинное (максимум {MAX_DESCRIPTION_LENGTH} символов)"
            else:
                try:
                    error_msg = error_msg.format(max_length=MAX_DESCRIPTION_LENGTH)
                except (KeyError, ValueError):
                    error_msg = f"Описание слишком длинное (максимум {MAX_DESCRIPTION_LENGTH} символов)"
            return False, error_msg
        
        success_msg = get_text("validation.description_valid", language=language)
        if success_msg == "validation.description_valid":  # Fallback если ключ не найден
            success_msg = "Описание корректно"
        return True, success_msg
    
    @staticmethod
    def validate_apartment(apartment: str, language: str = "ru") -> Tuple[bool, str]:
        """
        Валидация номера квартиры
        
        Args:
            apartment: Номер квартиры для валидации
            language: Язык для сообщений об ошибках (ru/uz)
            
        Returns:
            Tuple[bool, str]: (валиден ли номер квартиры, сообщение)
        """
        from uk_management_bot.utils.helpers import get_text
        
        if not apartment:
            success_msg = get_text("validation.apartment_optional", language=language)
            if success_msg == "validation.apartment_optional":  # Fallback если ключ не найден
                success_msg = "Номер квартиры необязателен"
            return True, success_msg
        
        if len(apartment) > MAX_APARTMENT_LENGTH:
            error_msg = get_text("validation.apartment_too_long", language=language, max_length=MAX_APARTMENT_LENGTH)
            if error_msg == "validation.apartment_too_long":  # Fallback если ключ не найден
                error_msg = f"Номер квартиры слишком длинный (максимум {MAX_APARTMENT_LENGTH} символов)"
            else:
                try:
                    error_msg = error_msg.format(max_length=MAX_APARTMENT_LENGTH)
                except (KeyError, ValueError):
                    error_msg = f"Номер квартиры слишком длинный (максимум {MAX_APARTMENT_LENGTH} символов)"
            return False, error_msg
        
        # Проверяем, что номер содержит только цифры и буквы
        if not re.match(r'^[0-9A-Za-z\-]+$', apartment):
            error_msg = get_text("validation.apartment_invalid_chars", language=language)
            if error_msg == "validation.apartment_invalid_chars":  # Fallback если ключ не найден
                error_msg = "Номер квартиры может содержать только цифры, буквы и дефис"
            return False, error_msg
        
        success_msg = get_text("validation.apartment_valid", language=language)
        if success_msg == "validation.apartment_valid":  # Fallback если ключ не найден
            success_msg = "Номер квартиры корректен"
        return True, success_msg
    
    @staticmethod
    def validate_category(category: str, language: str = "ru") -> Tuple[bool, str]:
        """
        Валидация категории заявки
        
        TASK 17 Этап B: Работает с внутренними ключами категорий вместо русских текстов.
        Поддерживает обратную совместимость с legacy данными через resolve_category_key.
        
        Args:
            category: Внутренний ключ категории или legacy текст
            language: Язык для сообщений об ошибках (ru/uz)
            
        Returns:
            Tuple[bool, str]: (валидна ли категория, сообщение)
        """
        from uk_management_bot.utils.helpers import get_text
        from uk_management_bot.keyboards.requests import (
            CATEGORY_INTERNAL_KEYS,
            resolve_category_key,
            get_category_display
        )
        
        if not category:
            error_msg = get_text("errors.category_empty", language=language)
            if error_msg == "errors.category_empty":  # Fallback если ключ не найден
                error_msg = "Категория не может быть пустой"
            return False, error_msg
        
        # TASK 17 Этап B: Разрешаем legacy тексты в внутренние ключи
        category_key = resolve_category_key(category)
        
        # Проверяем, что это валидный внутренний ключ
        if category_key not in CATEGORY_INTERNAL_KEYS:
            # Получаем список доступных категорий на языке пользователя
            available_categories = [
                get_category_display(key, language=language)
                for key in CATEGORY_INTERNAL_KEYS
            ]
            categories_list = ", ".join(available_categories)
            
            error_msg = get_text("errors.invalid_category", language=language)
            if error_msg == "errors.invalid_category":  # Fallback если ключ не найден
                error_msg = f"Неверная категория. Доступные категории: {categories_list}"
            else:
                # Подставляем список категорий в сообщение, если есть placeholder
                # TASK 17 Fix: Безопасная подстановка с обработкой KeyError
                # Если в locale файле есть другие плейсхолдеры, используем fallback
                try:
                    error_msg = error_msg.format(categories=categories_list)
                except (KeyError, ValueError) as e:
                    # Если формат строки содержит другие плейсхолдеры или неверный формат,
                    # используем простую конкатенацию как fallback
                    # TASK 17 Fix: Импортируем logger для логирования ошибки
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.warning(
                        f"Error formatting invalid_category message: {e}. "
                        f"Using fallback format. Original message: {error_msg}"
                    )
                    error_msg = f"{error_msg} Доступные категории: {categories_list}"
            
            return False, error_msg
        
        success_msg = get_text("validation.category_valid", language=language)
        if success_msg == "validation.category_valid":  # Fallback
            success_msg = "Категория корректна"
        
        return True, success_msg
    
    @staticmethod
    def validate_status(status: str, language: str = "ru") -> Tuple[bool, str]:
        """
        Валидация статуса заявки
        
        Args:
            status: Статус для валидации
            language: Язык для сообщений об ошибках (ru/uz)
            
        Returns:
            Tuple[bool, str]: (валиден ли статус, сообщение)
        """
        from uk_management_bot.utils.helpers import get_text
        
        if not status:
            error_msg = get_text("validation.status_empty", language=language)
            if error_msg == "validation.status_empty":  # Fallback если ключ не найден
                error_msg = "Статус не может быть пустым"
            return False, error_msg
        
        if status not in REQUEST_STATUSES:
            statuses_list = ", ".join(REQUEST_STATUSES)
            error_msg = get_text("validation.status_invalid", language=language, statuses=statuses_list)
            if error_msg == "validation.status_invalid":  # Fallback если ключ не найден
                error_msg = f"Неверный статус. Доступные статусы: {statuses_list}"
            else:
                try:
                    error_msg = error_msg.format(statuses=statuses_list)
                except (KeyError, ValueError):
                    error_msg = f"Неверный статус. Доступные статусы: {statuses_list}"
            return False, error_msg
        
        success_msg = get_text("validation.status_valid", language=language)
        if success_msg == "validation.status_valid":  # Fallback если ключ не найден
            success_msg = "Статус корректен"
        return True, success_msg
    
    @staticmethod
    def validate_role(role: str, language: str = "ru") -> Tuple[bool, str]:
        """
        Валидация роли пользователя
        
        Args:
            role: Роль для валидации
            language: Язык для сообщений об ошибках (ru/uz)
            
        Returns:
            Tuple[bool, str]: (валидна ли роль, сообщение)
        """
        from uk_management_bot.utils.helpers import get_text
        
        if not role:
            error_msg = get_text("validation.role_empty", language=language)
            if error_msg == "validation.role_empty":  # Fallback если ключ не найден
                error_msg = "Роль не может быть пустой"
            return False, error_msg
        
        if role not in USER_ROLES:
            roles_list = ", ".join(USER_ROLES)
            error_msg = get_text("validation.role_invalid", language=language, roles=roles_list)
            if error_msg == "validation.role_invalid":  # Fallback если ключ не найден
                error_msg = f"Неверная роль. Доступные роли: {roles_list}"
            else:
                try:
                    error_msg = error_msg.format(roles=roles_list)
                except (KeyError, ValueError):
                    error_msg = f"Неверная роль. Доступные роли: {roles_list}"
            return False, error_msg
        
        success_msg = get_text("validation.role_valid", language=language)
        if success_msg == "validation.role_valid":  # Fallback если ключ не найден
            success_msg = "Роль корректна"
        return True, success_msg
    
    @staticmethod
    def validate_urgency(urgency: str, language: str = "ru") -> Tuple[bool, str]:
        """
        Валидация срочности
        
        TASK 17: Использует внутренние ключи из URGENCY_KEYS вместо русских строк
        для обеспечения совместимости с локализованными клавиатурами.
        
        Args:
            urgency: Внутренний ключ срочности (low, medium, high, critical) или legacy текст
            language: Язык для сообщений об ошибках (ru/uz)
            
        Returns:
            Tuple[bool, str]: (валидна ли срочность, сообщение)
        """
        from uk_management_bot.utils.helpers import get_text
        from uk_management_bot.keyboards.requests import URGENCY_INTERNAL_KEYS, get_urgency_display
        
        if not urgency:
            error_msg = get_text("validation.urgency_empty", language=language)
            if error_msg == "validation.urgency_empty":  # Fallback если ключ не найден
                error_msg = "Срочность не может быть пустой"
            return False, error_msg
        
        # TASK 17: канон — внутренние ключи. legacy-рус нормализуем через
        # единый normalize_urgency (без дублирующей мапы — см. constants).
        from uk_management_bot.utils.constants import normalize_urgency
        urgency_key = normalize_urgency(urgency) or urgency
        
        if urgency_key not in URGENCY_INTERNAL_KEYS:
            # Получаем список доступных срочностей на языке пользователя
            available_urgencies = [
                get_urgency_display(key, language=language)
                for key in URGENCY_INTERNAL_KEYS
            ]
            urgencies_list = ", ".join(available_urgencies)
            
            error_msg = get_text("validation.urgency_invalid", language=language, urgencies=urgencies_list)
            if error_msg == "validation.urgency_invalid":  # Fallback если ключ не найден
                error_msg = f"Неверная срочность. Доступные варианты: {urgencies_list}"
            else:
                try:
                    error_msg = error_msg.format(urgencies=urgencies_list)
                except (KeyError, ValueError):
                    error_msg = f"Неверная срочность. Доступные варианты: {urgencies_list}"
            return False, error_msg
        
        success_msg = get_text("validation.urgency_valid", language=language)
        if success_msg == "validation.urgency_valid":  # Fallback если ключ не найден
            success_msg = "Срочность корректна"
        return True, success_msg
    
    @staticmethod
    def validate_file_size(file_size: int, file_type: str = "document", language: str = "ru") -> Tuple[bool, str]:
        """
        Валидация размера файла
        
        Args:
            file_size: Размер файла в байтах
            file_type: Тип файла (photo, video, document)
            language: Язык для сообщений об ошибках (ru/uz)
            
        Returns:
            Tuple[bool, str]: (валиден ли размер файла, сообщение)
        """
        from uk_management_bot.utils.helpers import get_text
        
        max_sizes = {
            "photo": MAX_PHOTO_SIZE,
            "video": MAX_VIDEO_SIZE,
            "document": MAX_DOCUMENT_SIZE
        }
        
        max_size = max_sizes.get(file_type, MAX_DOCUMENT_SIZE)
        
        if file_size > max_size:
            size_mb = max_size / (1024 * 1024)
            error_msg = get_text("validation.file_too_large", language=language, max_size_mb=int(size_mb))
            if error_msg == "validation.file_too_large":  # Fallback если ключ не найден
                error_msg = f"Файл слишком большой. Максимальный размер: {size_mb} MB"
            else:
                try:
                    error_msg = error_msg.format(max_size_mb=int(size_mb))
                except (KeyError, ValueError):
                    error_msg = f"Файл слишком большой. Максимальный размер: {size_mb} MB"
            return False, error_msg
        
        success_msg = get_text("validation.file_size_valid", language=language)
        if success_msg == "validation.file_size_valid":  # Fallback если ключ не найден
            success_msg = "Размер файла корректен"
        return True, success_msg
    
    @staticmethod
    def validate_rating(rating: int, language: str = "ru") -> Tuple[bool, str]:
        """
        Валидация оценки (1-5)
        
        Args:
            rating: Оценка для валидации
            language: Язык для сообщений об ошибках (ru/uz)
            
        Returns:
            Tuple[bool, str]: (валидна ли оценка, сообщение)
        """
        from uk_management_bot.utils.helpers import get_text
        
        if not isinstance(rating, int):
            error_msg = get_text("validation.rating_not_number", language=language)
            if error_msg == "validation.rating_not_number":  # Fallback если ключ не найден
                error_msg = "Оценка должна быть числом"
            return False, error_msg
        
        if rating < 1 or rating > 5:
            error_msg = get_text("validation.rating_out_of_range", language=language)
            if error_msg == "validation.rating_out_of_range":  # Fallback если ключ не найден
                error_msg = "Оценка должна быть от 1 до 5"
            return False, error_msg
        
        success_msg = get_text("validation.rating_valid", language=language)
        if success_msg == "validation.rating_valid":  # Fallback если ключ не найден
            success_msg = "Оценка корректна"
        return True, success_msg
    
    @staticmethod
    def validate_media_files_count(count: int, language: str = "ru") -> Tuple[bool, str]:
        """
        Валидация количества медиафайлов
        
        Args:
            count: Количество файлов
            language: Язык для сообщений об ошибках (ru/uz)
            
        Returns:
            Tuple[bool, str]: (валидно ли количество файлов, сообщение)
        """
        from uk_management_bot.utils.helpers import get_text
        from uk_management_bot.utils.constants import MAX_MEDIA_FILES_PER_REQUEST
        
        if count > MAX_MEDIA_FILES_PER_REQUEST:
            error_msg = get_text("validation.too_many_files", language=language, max_count=MAX_MEDIA_FILES_PER_REQUEST)
            if error_msg == "validation.too_many_files":  # Fallback если ключ не найден
                error_msg = f"Слишком много файлов. Максимум: {MAX_MEDIA_FILES_PER_REQUEST}"
            else:
                try:
                    error_msg = error_msg.format(max_count=MAX_MEDIA_FILES_PER_REQUEST)
                except (KeyError, ValueError):
                    error_msg = f"Слишком много файлов. Максимум: {MAX_MEDIA_FILES_PER_REQUEST}"
            return False, error_msg
        
        success_msg = get_text("validation.files_count_valid", language=language)
        if success_msg == "validation.files_count_valid":  # Fallback если ключ не найден
            success_msg = "Количество файлов корректно"
        return True, success_msg
    
    @staticmethod
    def validate_media_file(file_size: int, file_type: str) -> bool:
        """Валидация медиафайла (упрощенная версия для FSM)"""
        max_size = 20 * 1024 * 1024  # 20MB
        allowed_types = ['photo', 'video']
        return file_size <= max_size and file_type in allowed_types
    
    @staticmethod
    def sanitize_text(text: str) -> str:
        """Очистка текста от потенциально опасных символов"""
        # Удаляем HTML теги
        text = re.sub(r'<[^>]+>', '', text)
        
        # Удаляем множественные пробелы
        text = re.sub(r'\s+', ' ', text)
        
        # Удаляем пробелы в начале и конце
        text = text.strip()
        
        return text
    
    @staticmethod
    def validate_request_data(data: dict, language: str = "ru") -> Tuple[bool, str]:
        """
        Валидация всех данных заявки
        
        Args:
            data: Словарь с данными заявки
            language: Язык для сообщений об ошибках (ru/uz)
            
        Returns:
            Tuple[bool, str]: (валидны ли все данные, сообщение)
        """
        from uk_management_bot.utils.helpers import get_text
        
        required_fields = ['category', 'address', 'description']
        
        for field in required_fields:
            if field not in data or not data[field]:
                error_msg = get_text("validation.field_required", language=language, field=field)
                if error_msg == "validation.field_required":  # Fallback если ключ не найден
                    error_msg = f"Поле '{field}' обязательно для заполнения"
                else:
                    try:
                        error_msg = error_msg.format(field=field)
                    except (KeyError, ValueError):
                        error_msg = f"Поле '{field}' обязательно для заполнения"
                return False, error_msg
        
        # Проверяем категорию
        # TASK 17 Этап B: Передаём язык для локализованных сообщений об ошибках
        is_valid, message = Validator.validate_category(data['category'], language=language)
        if not is_valid:
            return False, message

        # Базовая проверка адреса (адреса теперь выбираются из справочника)
        if 'address' not in data or not data['address'] or len(str(data['address']).strip()) < 5:
            error_msg = get_text("validation.address_empty", language=language)
            if error_msg == "validation.address_empty":  # Fallback если ключ не найден
                error_msg = "Адрес не может быть пустым"
            return False, error_msg

        # Проверяем описание
        is_valid, message = Validator.validate_description(data['description'], language=language)
        if not is_valid:
            return False, message
        
        # Проверяем квартиру (если указана)
        if 'apartment' in data and data['apartment']:
            is_valid, message = Validator.validate_apartment(data['apartment'], language=language)
            if not is_valid:
                return False, message
        
        # Проверяем срочность (если указана)
        if 'urgency' in data and data['urgency']:
            is_valid, message = Validator.validate_urgency(data['urgency'], language=language)
            if not is_valid:
                return False, message
        
        success_msg = get_text("validation.all_data_valid", language=language)
        if success_msg == "validation.all_data_valid":  # Fallback если ключ не найден
            success_msg = "Все данные корректны"
        return True, success_msg

# Упрощенные функции валидации для FSM
def validate_description(description: str) -> bool:
    """Валидация описания (упрощенная версия для FSM)"""
    return len(description.strip()) >= 20

def validate_apartment(apartment: str) -> bool:
    """Валидация номера квартиры (упрощенная версия для FSM)"""
    return apartment.isdigit() and len(apartment) > 0

def validate_media_file(file_size: int, file_type: str) -> bool:
    """Валидация медиафайла (упрощенная версия для FSM)"""
    max_size = 20 * 1024 * 1024  # 20MB
    allowed_types = ['photo', 'video']
    return file_size <= max_size and file_type in allowed_types
