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
    def validate_phone(phone: str) -> Tuple[bool, str]:
        """Валидация номера телефона"""
        if not phone:
            return False, "Номер телефона не может быть пустым"
        
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
                return True, "Номер телефона корректен"
        
        return False, "Неверный формат номера телефона"
    
    @staticmethod
    def validate_description(description: str) -> Tuple[bool, str]:
        """Валидация описания"""
        if not description:
            return False, "Описание не может быть пустым"
        
        if len(description.strip()) < 10:
            return False, "Описание должно содержать минимум 10 символов"
        
        if len(description) > MAX_DESCRIPTION_LENGTH:
            return False, f"Описание слишком длинное (максимум {MAX_DESCRIPTION_LENGTH} символов)"
        
        return True, "Описание корректно"
    
    @staticmethod
    def validate_apartment(apartment: str) -> Tuple[bool, str]:
        """Валидация номера квартиры"""
        if not apartment:
            return True, "Номер квартиры необязателен"
        
        if len(apartment) > MAX_APARTMENT_LENGTH:
            return False, f"Номер квартиры слишком длинный (максимум {MAX_APARTMENT_LENGTH} символов)"
        
        # Проверяем, что номер содержит только цифры и буквы
        if not re.match(r'^[0-9A-Za-z\-]+$', apartment):
            return False, "Номер квартиры может содержать только цифры, буквы и дефис"
        
        return True, "Номер квартиры корректен"
    
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
    def validate_status(status: str) -> Tuple[bool, str]:
        """Валидация статуса заявки"""
        if not status:
            return False, "Статус не может быть пустым"
        
        if status not in REQUEST_STATUSES:
            return False, f"Неверный статус. Доступные статусы: {', '.join(REQUEST_STATUSES)}"
        
        return True, "Статус корректен"
    
    @staticmethod
    def validate_role(role: str) -> Tuple[bool, str]:
        """Валидация роли пользователя"""
        if not role:
            return False, "Роль не может быть пустой"
        
        if role not in USER_ROLES:
            return False, f"Неверная роль. Доступные роли: {', '.join(USER_ROLES)}"
        
        return True, "Роль корректна"
    
    @staticmethod
    def validate_urgency(urgency: str) -> Tuple[bool, str]:
        """Валидация срочности"""
        valid_urgencies = ["Обычная", "Средняя", "Срочная", "Критическая"]
        
        if not urgency:
            return False, "Срочность не может быть пустой"
        
        if urgency not in valid_urgencies:
            return False, f"Неверная срочность. Доступные варианты: {', '.join(valid_urgencies)}"
        
        return True, "Срочность корректна"
    
    @staticmethod
    def validate_file_size(file_size: int, file_type: str = "document") -> Tuple[bool, str]:
        """Валидация размера файла"""
        max_sizes = {
            "photo": MAX_PHOTO_SIZE,
            "video": MAX_VIDEO_SIZE,
            "document": MAX_DOCUMENT_SIZE
        }
        
        max_size = max_sizes.get(file_type, MAX_DOCUMENT_SIZE)
        
        if file_size > max_size:
            size_mb = max_size / (1024 * 1024)
            return False, f"Файл слишком большой. Максимальный размер: {size_mb} MB"
        
        return True, "Размер файла корректен"
    
    @staticmethod
    def validate_rating(rating: int) -> Tuple[bool, str]:
        """Валидация оценки (1-5)"""
        if not isinstance(rating, int):
            return False, "Оценка должна быть числом"
        
        if rating < 1 or rating > 5:
            return False, "Оценка должна быть от 1 до 5"
        
        return True, "Оценка корректна"
    
    @staticmethod
    def validate_media_files_count(count: int) -> Tuple[bool, str]:
        """Валидация количества медиафайлов"""
        from uk_management_bot.utils.constants import MAX_MEDIA_FILES_PER_REQUEST
        
        if count > MAX_MEDIA_FILES_PER_REQUEST:
            return False, f"Слишком много файлов. Максимум: {MAX_MEDIA_FILES_PER_REQUEST}"
        
        return True, "Количество файлов корректно"
    
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
    def validate_request_data(data: dict) -> Tuple[bool, str]:
        """Валидация всех данных заявки"""
        required_fields = ['category', 'address', 'description']
        
        for field in required_fields:
            if field not in data or not data[field]:
                return False, f"Поле '{field}' обязательно для заполнения"
        
        # Проверяем категорию
        # TASK 17 Этап B: Передаём язык для локализованных сообщений об ошибках
        # По умолчанию используем русский, так как validate_request_data не имеет параметра language
        is_valid, message = Validator.validate_category(data['category'], language="ru")
        if not is_valid:
            return False, message

        # Базовая проверка адреса (адреса теперь выбираются из справочника)
        if 'address' not in data or not data['address'] or len(str(data['address']).strip()) < 5:
            return False, "Адрес не может быть пустым"

        # Проверяем описание
        is_valid, message = Validator.validate_description(data['description'])
        if not is_valid:
            return False, message
        
        # Проверяем квартиру (если указана)
        if 'apartment' in data and data['apartment']:
            is_valid, message = Validator.validate_apartment(data['apartment'])
            if not is_valid:
                return False, message
        
        # Проверяем срочность (если указана)
        if 'urgency' in data and data['urgency']:
            is_valid, message = Validator.validate_urgency(data['urgency'])
            if not is_valid:
                return False, message
        
        return True, "Все данные корректны"

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
