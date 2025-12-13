#!/usr/bin/env python3
"""
Скрипт для объединения дополнительных ключей локализации
"""
import json
import os

def merge_additional_keys():
    """Объединяет дополнительные ключи локализации с основными файлами"""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Пути к файлам
    ru_main_path = os.path.join(base_dir, "uk_management_bot/config/locales/ru.json")
    uz_main_path = os.path.join(base_dir, "uk_management_bot/config/locales/uz.json")
    
    # Дополнительные ключи для русского языка
    ru_additional_keys = {
        "buttons": {
            "add_apartment": "➕ Добавить квартиру",
            "search_apartment": "🔍 Поиск квартиры",
            "back_to_menu": "◀️ Назад",
            "back_to_selection": "◀️ Назад к выбору",
            "all_selected": "✅ Все выбранные",
            "clear": "❌ Очистить",
            "select_all": "🔘 Выбрать все",
            "create_plan": "✅ Создать план",
            "additional_settings": "⚙️ Дополнительные настройки",
            "preview": "📋 Предпросмотр",
            "coverage_247": "🌙 24/7 покрытие",
            "balance_load": "⚖️ Балансировка нагрузки",
            "edit_specializations": "✏️ Изменить специализации",
            "change_period": "📅 Изменить период",
            "detailed_stats": "📊 Подробная статистика",
            "export_schedule": "📋 Экспорт расписания",
            "notify_employees": "👥 Уведомить сотрудников",
            "resolve_conflicts": "⚠️ Разрешить конфликты",
            "edit_plan": "✏️ Корректировать план",
            "recalculate": "🔄 Пересчитать",
            "create_new_plan": "📅 Создать новый план",
            "analytics": "📈 Аналитика",
            "main_menu": "🏠 Главное меню",
            "active_transfers": "🔄 Активные передачи",
            "pending_transfers": "⏳ Ожидающие передачи",
            "transfer_history": "✅ История передач",
            "initiate_transfer": "➕ Инициализировать передачу",
            "search_transfers": "🔍 Поиск передач",
            "efficiency": "📊 Эффективность планов",
            "workload": "👥 Загруженность сотрудников",
            "coverage": "🎯 Покрытие специализаций",
            "timing_metrics": "⏱️ Временные метрики",
            "recommendations": "💡 Рекомендации",
            "export_report": "📈 Экспорт отчета",
            "back": "🔙 Назад",
            "view_media": "📎 Просмотреть медиа",
            "assign_request": "📝 Назначить заявку",
            "view_assignments": "👥 Просмотр назначений",
            "add_comment": "📝 Добавить комментарий",
            "change_status": "🔄 Изменить статус",
            "my_requests": "📋 Мои заявки",
            "statistics": "📊 Статистика",
            "back_to_requests": "🔙 Назад к заявкам",
            "purchase_materials": "🛒 Закупка материалов",
            "request_clarification": "❓ Запросить уточнение",
            "complete_work": "✅ Завершить работу",
            "return_to_work": "🔄 Вернуться к работе",
            "yes_complete": "✅ Да, завершить",
            "cancel": "❌ Отмена",
            "confirm_assignment": "📋 Назначить заявку",
            "view_comments": "📋 Просмотр комментариев",
            "media": "📎 Медиа",
            "phone_required": "📱 Указать телефон",
            "upload_documents": "📄 Загрузить документы",
            "complete_without_docs": "✅ Завершить без документов"
        },
        "validation": {
            "description_empty": "Описание не может быть пустым",
            "description_too_short": "Описание должно содержать минимум 10 символов",
            "description_too_long": "Описание слишком длинное (максимум {MAX_DESCRIPTION_LENGTH} символов)",
            "description_correct": "Описание корректно",
            "apartment_optional": "Номер квартиры необязателен",
            "apartment_too_long": "Номер квартиры слишком длинный (максимум {MAX_APARTMENT_LENGTH} символов)",
            "apartment_invalid_chars": "Номер квартиры может содержать только цифры, буквы и дефис",
            "apartment_correct": "Номер квартиры корректен",
            "category_empty": "Категория не может быть пустой",
            "invalid_category": "Неверная категория. Доступные категории: {categories_list}",
            "category_correct": "Категория корректна",
            "status_empty": "Статус не может быть пустым",
            "invalid_status": "Неверный статус: {new_status}",
            "completed": "Выполнена",
            "in_work": "В работе",
            "purchase": "Закуп",
            "clarification": "Уточнение",
            "cancelled": "Отменена",
            "accepted": "Принято",
            "in_progress": "Исполнено",
            "phone_empty": "Номер телефона не может быть пустым",
            "phone_valid": "Номер телефона корректен",
            "phone_invalid_format": "Неверный формат номера телефона",
            "address_empty": "Адрес не может быть пустым",
            "description_too_short_or_long": "Описание слишком короткое или длинное",
            "new": "Новая",
            "invalid_category_key": "Неверная категория: {category} (разрешено в ключ: {category_key})",
            "invalid_urgency": "Неверная срочность: {urgency}",
            "user_by_telegram_id": "Получение пользователя по Telegram ID",
            "added_statuses": "Добавлены статусы \"Выполнено\" и \"Принято\"",
            "removed_status": "Удален старый статус \"Подтверждена\"",
            "status_transitions": {
                "Новая": ["В работе", "Закуп", "Уточнение", "Отменена"],
                "В работе": ["Уточнение", "Закуп", "Выполнена", "Отменена"],
                "Уточнение": ["В работе", "Закуп", "Выполнена", "Отменена"],
                "Закуп": ["В работе", "Уточнение", "Выполнена", "Отменена"],
                "Выполнена": ["Принято", "В работе", "Отменена"],
                "Принято": [],
                "Отменена": []
            }
        },
        "created_label": "Создана:",
        "description_empty": "Описание не может быть пустым",
        "description_too_short": "Описание должно содержать минимум 10 символов",
        "description_too_long": "Описание слишком длинное (максимум {MAX_DESCRIPTION_LENGTH} символов)",
        "description_correct": "Описание корректно",
        "apartment_optional": "Номер квартиры необязателен",
        "apartment_too_long": "Номер квартиры слишком длинный (максимум {MAX_APARTMENT_LENGTH} символов)",
        "apartment_invalid_chars": "Номер квартиры может содержать только цифры, буквы и дефис",
        "apartment_correct": "Номер квартиры корректен",
        "category_empty": "Категория не может быть пустой",
        "invalid_category": "Неверная категория. Доступные категории: {categories_list}",
        "category_correct": "Категория корректна",
        "status_empty": "Статус не может быть пустым",
        "invalid_status": "Неверный статус: {new_status}",
        "completed": "Выполнена",
        "in_work": "В работе",
        "purchase": "Закуп",
        "clarification": "Уточнение",
        "cancelled": "Отменена",
        "accepted": "Принято",
        "in_progress": "Исполнено",
        "phone_empty": "Номер телефона не может быть пустым",
        "phone_valid": "Номер телефона корректен",
        "phone_invalid_format": "Неверный формат номера телефона",
        "address_empty": "Адрес не может быть пустым",
        "description_too_short_or_long": "Описание слишком короткое или длинное",
        "new": "Новая",
        "invalid_category_key": "Неверная категория: {category} (разрешено в ключ: {category_key})",
        "invalid_urgency": "Неверная срочность: {urgency}",
        "user_by_telegram_id": "Получение пользователя по Telegram ID",
        "added_statuses": "Добавлены статусы \"Выполнено\" и \"Принято\"",
        "removed_status": "Удален старый статус \"Подтверждена\"",
        "status_transitions": {
            "Новая": ["В работе", "Закуп", "Уточнение", "Отменена"],
            "В работе": ["Уточнение", "Закуп", "Выполнена", "Отменена"],
            "Уточнение": ["В работе", "Закуп", "Выполнена", "Отменена"],
            "Закуп": ["В работе", "Уточнение", "Выполнена", "Отменена"],
            "Выполнена": ["Принято", "В работе", "Отменена"],
            "Принято": [],
            "Отменена": []
        }
    }
    
    # Объединяем ключи для русского языка
    for section, keys in ru_additional_keys.items():
        if section not in ru_data:
            ru_data[section] = {}
        ru_data[section].update(keys)
    
    # Создаем узбекские ключи на основе русских
    for section, keys in ru_additional_keys.items():
        if section not in uz_data:
            uz_data[section] = {}
        uz_data[section].update(keys)
    
    # Сохраняем обновленные файлы
    with open(ru_main_path, 'w', encoding='utf-8') as f:
        json.dump(ru_data, f, ensure_ascii=False, indent=2)
    
    with open(uz_main_path, 'w', encoding='utf-8') as f:
        json.dump(uz_data, f, ensure_ascii=False, indent=2)
    
    print("Дополнительные ключи локализации успешно объединены!")

if __name__ == "__main__":
    merge_additional_keys()
