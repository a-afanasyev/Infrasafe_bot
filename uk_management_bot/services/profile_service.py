"""
Сервис для работы с профилем пользователя
"""
import json
import logging
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from uk_management_bot.database.models.user import User
from uk_management_bot.utils.helpers import get_text

logger = logging.getLogger(__name__)

class ProfileService:
    """Сервис для работы с профилем пользователя"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def get_user_profile_data(self, telegram_id: int) -> Optional[Dict[str, Any]]:
        """
        Получает полные данные профиля пользователя
        
        Args:
            telegram_id: ID пользователя в Telegram
            
        Returns:
            Словарь с данными профиля или None если пользователь не найден
        """
        try:
            user = self.db.query(User).filter(User.telegram_id == telegram_id).first()
            if not user:
                logger.warning(f"Пользователь с telegram_id={telegram_id} не найден")
                return None
            
            # Парсим роли из JSON
            roles = ["applicant"]  # дефолт
            try:
                if user.roles:
                    parsed_roles = json.loads(user.roles)
                    if isinstance(parsed_roles, list):
                        roles = [str(r) for r in parsed_roles if isinstance(r, str)]
            except (json.JSONDecodeError, TypeError):
                logger.warning(f"Ошибка парсинга ролей для пользователя {telegram_id}: {user.roles}")
            
            # Активная роль
            active_role = user.active_role or roles[0] if roles else "applicant"
            if active_role not in roles:
                active_role = roles[0] if roles else "applicant"
            
            # Парсим специализации (для исполнителей)
            specializations = []
            if user.specialization:
                # Поддерживаем CSV формат для множественных специализаций
                specializations = [s.strip() for s in user.specialization.split(',') if s.strip()]
            
            # Парсим дворы (множественные)
            yards = []
            if user.yard_address:
                # Поддерживаем разделитель ';' для множественных дворов
                yards = [y.strip() for y in user.yard_address.split(';') if y.strip()]
            
            profile_data = {
                'user_id': user.id,
                'telegram_id': user.telegram_id,
                'username': user.username,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'roles': roles,
                'active_role': active_role,
                'status': user.status or 'pending',
                'language': user.language or 'ru',
                'phone': user.phone,
                'home_address': user.home_address,
                'apartment_address': user.apartment_address,
                'yard_address': user.yard_address,
                'yards': yards,  # массив дворов
                'specializations': specializations,  # массив специализаций
                'created_at': user.created_at,
                'updated_at': user.updated_at
            }
            
            # Логируем данные адресов для отладки
            logger.info(f"Данные адресов для пользователя {telegram_id}:")
            logger.info(f"  home_address: '{user.home_address}'")
            logger.info(f"  apartment_address: '{user.apartment_address}'")
            logger.info(f"  yard_address: '{user.yard_address}'")
            logger.info(f"  yards array: {yards}")
            
            logger.info(f"Получены данные профиля для пользователя {telegram_id}")
            return profile_data
            
        except Exception as e:
            logger.error(f"Ошибка получения данных профиля для {telegram_id}: {e}")
            return None
    
    def format_profile_text(self, profile_data: Dict[str, Any], language: str = "ru") -> str:
        """
        Форматирует данные профиля в текст для отображения
        
        Args:
            profile_data: Данные профиля
            language: Язык локализации
            
        Returns:
            Отформатированный текст профиля
        """
        if not profile_data:
            return get_text("errors.unknown_error", language=language)
        
        # Заголовок
        title = get_text("profile.title", language=language)
        text_parts = [title, ""]
        
        # Имя пользователя
        full_name = []
        if profile_data.get('first_name'):
            full_name.append(profile_data['first_name'])
        if profile_data.get('last_name'):
            full_name.append(profile_data['last_name'])
        
        if full_name:
            text_parts.append(f"👤 {' '.join(full_name)}")
        if profile_data.get('username'):
            text_parts.append(f"📱 @{profile_data['username']}")
        
        text_parts.append("")  # пустая строка
        
        # Статус пользователя
        status = profile_data.get('status', 'pending')
        status_text = get_text(f"user_status.{status}", language=language)
        text_parts.append(f"{get_text('profile.status', language=language)} {status_text}")
        
        # Активная роль
        active_role = profile_data.get('active_role', 'applicant')
        active_role_text = get_text(f"roles.{active_role}", language=language)
        text_parts.append(f"{get_text('profile.active_role', language=language)} {active_role_text}")
        
        # Все доступные роли
        roles = profile_data.get('roles', ['applicant'])
        if len(roles) > 1:
            roles_text = [get_text(f"roles.{role}", language=language) for role in roles]
            text_parts.append(f"{get_text('profile.all_roles', language=language)} {', '.join(roles_text)}")
        
        # Телефон
        phone = profile_data.get('phone')
        phone_text = phone if phone else get_text("profile.phone_not_set", language=language)
        text_parts.append(f"{get_text('profile.phone', language=language)} {phone_text}")
        
        # Специализация (для исполнителей/менеджеров)
        if 'executor' in roles or 'manager' in roles:
            specializations = profile_data.get('specializations', [])
            if specializations:
                spec_texts = [get_text(f"specializations.{spec}", language=language) for spec in specializations]
                text_parts.append(f"{get_text('profile.specialization', language=language)} {', '.join(spec_texts)}")
            else:
                text_parts.append(f"{get_text('profile.specialization', language=language)} {get_text('profile.no_specialization', language=language)}")
        
        # Адреса
        text_parts.append("")  # пустая строка
        text_parts.append(f"🏠 {get_text('profile.addresses', language=language)}")
        
        # Адрес дома
        home_addr = profile_data.get('home_address')
        home_text = home_addr if home_addr else get_text("profile.address_not_set", language=language)
        home_label = get_text('profile.home_address', language=language)
        if home_label == 'profile.home_address':  # если ключ не найден
            home_label = "Адрес дома:" if language == "ru" else "Uy manzili:"
        text_parts.append(f"  {home_label} {home_text}")
        
        # Логируем для отладки
        logger.info(f"Форматирование адреса дома: addr='{home_addr}', text='{home_text}', label='{home_label}'")
        
        # Адрес квартиры
        apt_addr = profile_data.get('apartment_address')
        if apt_addr:
            apt_label = get_text('profile.apartment_address', language=language)
            if apt_label == 'profile.apartment_address':  # если ключ не найден
                apt_label = "Адрес квартиры:" if language == "ru" else "Xona manzili:"
            text_parts.append(f"  {apt_label} {apt_addr}")
            logger.info(f"Форматирование адреса квартиры: addr='{apt_addr}', label='{apt_label}'")
        else:
            logger.info(f"Адрес квартиры не заполнен")
        
        # Адрес двора
        yard_addr = profile_data.get('yard_address')
        if yard_addr:
            yard_label = get_text('profile.yard_address', language=language)
            if yard_label == 'profile.yard_address':  # если ключ не найден
                yard_label = "Двор:" if language == "ru" else "Hovli:"
            text_parts.append(f"  {yard_label} {yard_addr}")
        
        # Дворы (множественные) - если есть массив дворов
        yards = profile_data.get('yards', [])
        if yards and len(yards) > 1:
            yard_label = get_text('profile.yard_address', language=language)
            if yard_label == 'profile.yard_address':  # если ключ не найден
                yard_label = "Двор:" if language == "ru" else "Hovli:"
            text_parts.append(f"  {yard_label} {get_text('profile.multiple_yards', language=language)}")
            for i, yard in enumerate(yards, 1):
                text_parts.append(f"    {i}. {yard}")
        
        # Язык
        text_parts.append("")  # пустая строка
        lang_display = "🇷🇺 Русский" if language == "ru" else "🇺🇿 O'zbek"
        text_parts.append(f"{get_text('profile.language', language=language)} {lang_display}")
        
        return "\n".join(text_parts)
    
    def validate_profile_data(self, profile_data: Dict[str, Any]) -> List[str]:
        """
        Валидирует данные профиля и возвращает список проблем
        
        Args:
            profile_data: Данные профиля
            
        Returns:
            Список строк с описанием проблем (пустой если всё ОК)
        """
        issues = []
        
        if not profile_data:
            issues.append("Данные профиля отсутствуют")
            return issues
        
        # Проверяем обязательные поля
        if not profile_data.get('telegram_id'):
            issues.append("Отсутствует telegram_id")
        
        if not profile_data.get('roles') or not isinstance(profile_data['roles'], list):
            issues.append("Некорректные роли")
        
        if profile_data.get('active_role') not in profile_data.get('roles', []):
            issues.append("Активная роль не входит в список доступных ролей")
        
        if profile_data.get('status') not in ['pending', 'approved', 'blocked']:
            issues.append("Некорректный статус пользователя")
        
        # Проверяем телефон (если указан)
        phone = profile_data.get('phone')
        if phone and (len(phone) < 10 or not phone.replace('+', '').replace(' ', '').replace('-', '').isdigit()):
            issues.append("Некорректный формат телефона")
        
        return issues
