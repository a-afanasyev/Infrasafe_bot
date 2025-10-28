"""
Клавиатуры для исполнителей - интерфейс "Мои смены"
"""

from datetime import datetime, date, timedelta
from typing import List, Optional, Dict, Any

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from uk_management_bot.database.models.shift import Shift


def get_my_shifts_menu(lang: str = "ru") -> InlineKeyboardMarkup:
    """Главное меню моих смен"""

    # Тексты для разных языков
    texts = {
        "ru": {
            "current": "🔥 Текущие смены",
            "schedule": "📅 Расписание на неделю",
            "history": "📊 История смен",
            "time": "⏰ Учет времени",
            "stats": "📈 Моя статистика",
            "transfer": "🔄 Передача смен"
        },
        "uz": {
            "current": "🔥 Joriy smenalar",
            "schedule": "📅 Haftalik jadval",
            "history": "📊 Smenalar tarixi",
            "time": "⏰ Vaqt hisoboti",
            "stats": "📈 Mening statistikam",
            "transfer": "🔄 Smena o'tkazish"
        }
    }

    t = texts.get(lang, texts["ru"])

    keyboard = [
        [InlineKeyboardButton(text=t["current"], callback_data="view_current_shifts")],
        [InlineKeyboardButton(text=t["schedule"], callback_data="view_week_schedule")],
        [InlineKeyboardButton(text=t["history"], callback_data="shift_history")],
        [InlineKeyboardButton(text=t["time"], callback_data="time_tracking")],
        [InlineKeyboardButton(text=t["stats"], callback_data="my_statistics")],
        [InlineKeyboardButton(text=t["transfer"], callback_data="shift_transfer_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_shift_list_keyboard(shifts: List[Shift], lang: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура со списком смен"""
    keyboard = []
    
    for shift in shifts:
        # Формируем описание смены
        shift_date = shift.planned_start_time.date()
        today = date.today()
        tomorrow = today + timedelta(days=1)
        
        if shift_date == today:
            date_prefix = "🔥"
        elif shift_date == tomorrow:
            date_prefix = "📅"
        else:
            date_prefix = "📆"
        
        start_time = shift.planned_start_time.strftime("%H:%M")
        end_time = shift.planned_end_time.strftime("%H:%M") if shift.planned_end_time else "?"
        
        status_emoji = {
            'planned': '⏱️',
            'active': '🔴',
            'completed': '✅',
            'cancelled': '❌'
        }.get(shift.status, '⚪')
        
        # Краткое описание специализации
        spec_info = ""
        if shift.specialization_focus and len(shift.specialization_focus) > 0:
            spec_info = f" • {shift.specialization_focus[0]}"
            if len(shift.specialization_focus) > 1:
                spec_info += f" (+{len(shift.specialization_focus)-1})"
        
        button_text = f"{date_prefix} {start_time}-{end_time} {status_emoji}{spec_info}"
        
        keyboard.append([
            InlineKeyboardButton(
                text=button_text,
                callback_data=f"shift_details:{shift.id}"
            )
        ])
    
    # Кнопки навигации
    keyboard.extend([
        [InlineKeyboardButton(text="🔄 Обновить", callback_data="view_current_shifts")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_my_shifts")]
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_shift_actions_keyboard(shift: Shift, lang: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура действий со сменой"""
    keyboard = []

    # Тексты для разных языков
    texts = {
        "ru": {
            "start": "▶️ Начать смену",
            "contact": "📞 Связаться с менеджером",
            "decline": "❌ Отказаться от смены",
            "end": "🛑 Завершить смену",
            "requests": "📋 Мои заявки",
            "break": "⏸️ Сделать перерыв",
            "transfer": "🔄 Передать смену"
        },
        "uz": {
            "start": "▶️ Smenani boshlash",
            "contact": "📞 Menejer bilan bog'lanish",
            "decline": "❌ Smenadan voz kechish",
            "end": "🛑 Smenani tugatish",
            "requests": "📋 Mening zayavkalarim",
            "break": "⏸️ Tanaffus qilish",
            "transfer": "🔄 Smenani o'tkazish"
        }
    }

    t = texts.get(lang, texts["ru"])

    # Действия в зависимости от статуса смены
    if shift.status == 'planned':
        # Смена запланирована - можно начать или передать
        keyboard.extend([
            [InlineKeyboardButton(text=t["start"], callback_data="start_shift")],
            [InlineKeyboardButton(text=t["transfer"], callback_data=f"transfer_shift:{shift.id}")],
            [InlineKeyboardButton(text=t["contact"], callback_data=f"contact_manager:{shift.id}")],
            [InlineKeyboardButton(text=t["decline"], callback_data=f"decline_shift:{shift.id}")]
        ])
    
    elif shift.status == 'active':
        # Смена активна - можно завершить и работать с заявками
        keyboard.extend([
            [InlineKeyboardButton(text=t["end"], callback_data="end_shift")],
            [InlineKeyboardButton(text=t["requests"], callback_data=f"shift_requests:{shift.id}")],
            [InlineKeyboardButton(text=t["break"], callback_data="take_break")],
            [InlineKeyboardButton(text=t["transfer"], callback_data=f"transfer_shift:{shift.id}")]
        ])
        
        # Дополнительные действия
        keyboard.extend([
            [
                InlineKeyboardButton(text="📍 Отметить местоположение", callback_data="mark_location"),
                InlineKeyboardButton(text="📝 Добавить заметку", callback_data="add_note")
            ],
            [InlineKeyboardButton(text="🆘 Экстренная помощь", callback_data="emergency_help")]
        ])
    
    elif shift.status == 'completed':
        # Смена завершена - просмотр результатов
        keyboard.extend([
            [InlineKeyboardButton(text="📊 Отчет по смене", callback_data=f"view_shift_report:{shift.id}")],
            [InlineKeyboardButton(text="📋 Обработанные заявки", callback_data=f"completed_requests:{shift.id}")],
            [InlineKeyboardButton(text="💰 Расчет оплаты", callback_data=f"payment_calculation:{shift.id}")]
        ])
    
    # Общие действия (доступны всегда)
    keyboard.extend([
        [
            InlineKeyboardButton(text="ℹ️ Подробности", callback_data=f"shift_info:{shift.id}"),
            InlineKeyboardButton(text="📤 Поделиться", callback_data=f"share_shift:{shift.id}")
        ],
        [InlineKeyboardButton(text="🔙 Назад к списку", callback_data="view_current_shifts")]
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_shift_filter_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура фильтров смен"""
    keyboard = [
        [
            InlineKeyboardButton(text="📅 Сегодня", callback_data="filter_today"),
            InlineKeyboardButton(text="📅 Завтра", callback_data="filter_tomorrow")
        ],
        [
            InlineKeyboardButton(text="📆 Эта неделя", callback_data="filter_this_week"),
            InlineKeyboardButton(text="📆 Следующая неделя", callback_data="filter_next_week")
        ],
        [
            InlineKeyboardButton(text="⏱️ Запланированные", callback_data="filter_planned"),
            InlineKeyboardButton(text="🔴 Активные", callback_data="filter_active")
        ],
        [
            InlineKeyboardButton(text="✅ Завершенные", callback_data="filter_completed"),
            InlineKeyboardButton(text="🗂️ Все", callback_data="filter_all")
        ],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_my_shifts")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_time_tracking_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура учета времени"""
    keyboard = [
        [InlineKeyboardButton(text="⏱️ Начать учет времени", callback_data="start_time_tracking")],
        [InlineKeyboardButton(text="⏸️ Приостановить", callback_data="pause_time_tracking")],
        [InlineKeyboardButton(text="🛑 Остановить", callback_data="stop_time_tracking")],
        [InlineKeyboardButton(text="📊 Сводка времени", callback_data="time_summary")],
        [InlineKeyboardButton(text="📈 История учета", callback_data="time_history")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_my_shifts")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_statistics_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура статистики исполнителя"""
    keyboard = [
        [InlineKeyboardButton(text="📊 Статистика за неделю", callback_data="stats_week")],
        [InlineKeyboardButton(text="📈 Статистика за месяц", callback_data="stats_month")],
        [InlineKeyboardButton(text="📋 Обработанные заявки", callback_data="stats_requests")],
        [InlineKeyboardButton(text="⏰ Отработанное время", callback_data="stats_time")],
        [InlineKeyboardButton(text="🎯 Эффективность работы", callback_data="stats_efficiency")],
        [InlineKeyboardButton(text="🏆 Рейтинг и достижения", callback_data="stats_achievements")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_my_shifts")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_break_options_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура опций перерыва"""
    keyboard = [
        [InlineKeyboardButton(text="☕ Обеденный перерыв (30 мин)", callback_data="break_lunch")],
        [InlineKeyboardButton(text="🚬 Короткий перерыв (15 мин)", callback_data="break_short")],
        [InlineKeyboardButton(text="🏥 Медицинский перерыв", callback_data="break_medical")],
        [InlineKeyboardButton(text="⏰ Другая длительность", callback_data="break_custom")],
        [InlineKeyboardButton(text="🔙 Отмена", callback_data="cancel_break")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_emergency_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура экстренных ситуаций"""
    keyboard = [
        [InlineKeyboardButton(text="🚨 Вызвать экстренные службы", callback_data="call_emergency_services")],
        [InlineKeyboardButton(text="👮 Вызвать охрану", callback_data="call_security")],
        [InlineKeyboardButton(text="🔧 Техническая неисправность", callback_data="technical_issue")],
        [InlineKeyboardButton(text="🏥 Медицинская помощь", callback_data="medical_help")],
        [InlineKeyboardButton(text="📞 Связаться с диспетчером", callback_data="contact_dispatcher")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="cancel_emergency")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_shift_requests_keyboard(shift_id: int, lang: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура для работы с заявками смены"""
    keyboard = [
        [InlineKeyboardButton(text="📋 Все мои заявки", callback_data=f"all_requests:{shift_id}")],
        [InlineKeyboardButton(text="🔥 Новые заявки", callback_data=f"new_requests:{shift_id}")],
        [InlineKeyboardButton(text="🔴 В работе", callback_data=f"active_requests:{shift_id}")],
        [InlineKeyboardButton(text="✅ Завершенные", callback_data=f"completed_requests:{shift_id}")],
        [InlineKeyboardButton(text="📍 По местоположению", callback_data=f"requests_by_location:{shift_id}")],
        [InlineKeyboardButton(text="🔙 Назад к смене", callback_data=f"shift_details:{shift_id}")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_location_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура для отметки местоположения"""
    keyboard = [
        [InlineKeyboardButton(text="📍 Отправить текущее местоположение", callback_data="send_current_location")],
        [InlineKeyboardButton(text="🏠 Отметить адрес", callback_data="mark_address")],
        [InlineKeyboardButton(text="📋 История местоположений", callback_data="location_history")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_shift_actions")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_shift_completion_keyboard(shift_id: int, lang: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура завершения смены"""
    keyboard = [
        [InlineKeyboardButton(text="✅ Завершить смену", callback_data=f"confirm_end_shift:{shift_id}")],
        [InlineKeyboardButton(text="📝 Добавить отчет", callback_data=f"add_shift_report:{shift_id}")],
        [InlineKeyboardButton(text="📊 Итоги работы", callback_data=f"shift_summary:{shift_id}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data=f"cancel_end_shift:{shift_id}")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_navigation_keyboard(current_page: int, total_pages: int, callback_prefix: str, lang: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура навигации по страницам"""
    keyboard = []
    
    navigation_row = []
    
    # Кнопка "Предыдущая"
    if current_page > 1:
        navigation_row.append(
            InlineKeyboardButton(text="⬅️ Пред.", callback_data=f"{callback_prefix}:{current_page - 1}")
        )
    
    # Показатель страницы
    navigation_row.append(
        InlineKeyboardButton(text=f"{current_page}/{total_pages}", callback_data="page_info")
    )
    
    # Кнопка "Следующая"
    if current_page < total_pages:
        navigation_row.append(
            InlineKeyboardButton(text="След. ➡️", callback_data=f"{callback_prefix}:{current_page + 1}")
        )
    
    if navigation_row:
        keyboard.append(navigation_row)
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)