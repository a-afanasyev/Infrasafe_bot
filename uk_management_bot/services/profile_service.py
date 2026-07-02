"""
Сервис для работы с профилем пользователя
"""
import json
import logging
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from uk_management_bot.database.models.user import User
from uk_management_bot.utils.helpers import get_text
from uk_management_bot.utils.auth_helpers import parse_roles_safe

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
            
            # Парсим роли (COD-01: канонический парсер, JSON+CSV)
            roles = parse_roles_safe(user.roles) or ["applicant"]

            # Активная роль
            active_role = user.active_role or roles[0] if roles else "applicant"
            if active_role not in roles:
                active_role = roles[0] if roles else "applicant"
            
            # Парсим специализации (для исполнителей)
            specializations = []
            if user.specialization:
                # Поддерживаем CSV формат для множественных специализаций
                # Также обрабатываем JSON формат, если специализации хранятся как JSON строка
                spec_str = user.specialization.strip()
                
                # Сначала пробуем JSON парсинг
                if spec_str.startswith('[') or spec_str.startswith('{'):
                    try:
                        parsed = json.loads(spec_str)
                        if isinstance(parsed, list):
                            specializations = [str(s).strip() for s in parsed if s]
                        elif isinstance(parsed, dict):
                            specializations = [str(s).strip() for s in parsed.values() if s]
                    except (json.JSONDecodeError, TypeError):
                        # Если не валидный JSON, пробуем извлечь значения вручную
                        # Обрабатываем случаи типа: specializations.["electrician", specializations."repair"]
                        import re
                        # Ищем все значения в кавычках (и двойных, и одинарных)
                        # Используем более точное регулярное выражение для извлечения значений
                        matches = re.findall(r'["\']([^"\']+)["\']', spec_str)
                        if matches:
                            # Фильтруем значения, которые не являются ключами локализации
                            # Также очищаем от префиксов "specializations."
                            cleaned_matches = []
                            for m in matches:
                                cleaned = m.replace('specializations.', '').strip()
                                # Пропускаем пустые значения и значения, которые являются ключами локализации
                                if cleaned and not cleaned.startswith('specializations.') and cleaned not in cleaned_matches:
                                    cleaned_matches.append(cleaned)
                            specializations = cleaned_matches
                        else:
                            # Если не нашли кавычки, пробуем CSV
                            specializations = [s.strip() for s in spec_str.split(',') if s.strip()]
                else:
                    # CSV формат или простой список через запятую
                    specializations = [s.strip() for s in spec_str.split(',') if s.strip()]
                
                # Очищаем от префиксов "specializations." если они есть
                cleaned_specs = []
                for spec in specializations:
                    cleaned = spec.replace('specializations.', '').strip().strip('"').strip("'")
                    if cleaned and cleaned not in cleaned_specs:
                        cleaned_specs.append(cleaned)
                specializations = cleaned_specs

            # ОБНОВЛЕНО: Получаем адреса из новой системы квартир вместо устаревших полей
            apartments = []
            if user.user_apartments:
                for ua in user.user_apartments:
                    if ua.status == 'approved' and ua.apartment:
                        apartment_info = {
                            'id': ua.apartment.id,
                            'address': ua.apartment.full_address if hasattr(ua.apartment, 'full_address') else f"Квартира {ua.apartment.apartment_number}",
                            'is_primary': ua.is_primary,
                            'is_owner': ua.is_owner
                        }
                        apartments.append(apartment_info)

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
                'apartments': apartments,  # НОВОЕ: список одобренных квартир
                'specializations': specializations,  # массив специализаций
                'created_at': user.created_at,
                'updated_at': user.updated_at
            }

            # Логируем данные адресов для отладки
            logger.info(f"Данные адресов для пользователя {telegram_id}:")
            logger.info(f"  apartments count: {len(apartments)}")
            if apartments:
                logger.info(f"  primary apartment: {next((a['address'] for a in apartments if a['is_primary']), 'None')}")
            
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
                # Локализуем каждую специализацию, если ключ не найден - используем исходное значение
                spec_texts = []
                for spec in specializations:
                    # Очищаем от кавычек и скобок, если они есть
                    spec_clean = spec.strip().strip('"').strip("'").strip('[').strip(']')
                    localized = get_text(f"specializations.{spec_clean}", language=language)
                    # Если локализация не найдена (вернулся ключ), используем исходное значение
                    if localized == f"specializations.{spec_clean}":
                        spec_texts.append(spec_clean)
                    else:
                        spec_texts.append(localized)
                text_parts.append(f"{get_text('profile.specialization', language=language)} {', '.join(spec_texts)}")
            else:
                text_parts.append(f"{get_text('profile.specialization', language=language)} {get_text('profile.no_specialization', language=language)}")
        
        # ОБНОВЛЕНО: Адреса из новой системы квартир
        text_parts.append("")  # пустая строка
        text_parts.append(f"🏠 {get_text('profile.addresses', language=language)}")

        apartments = profile_data.get('apartments', [])
        if apartments:
            for apt in apartments:
                primary_marker = " ⭐" if apt.get('is_primary') else ""
                owner_marker = f" ({get_text('profile.owner', language=language)})" if apt.get('is_owner') else ""
                text_parts.append(f"  {apt['address']}{primary_marker}{owner_marker}")
            logger.info(f"Форматирование адресов квартир: {len(apartments)} квартир")
        else:
            text_parts.append(f"  {get_text('profile.no_addresses', language=language)}")
            logger.info("Адреса квартир не заполнены")
        
        # Язык
        text_parts.append("")  # пустая строка
        lang_display = get_text("profile.language_ru", language=language) if language == "ru" else get_text("profile.language_uz", language=language)
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
