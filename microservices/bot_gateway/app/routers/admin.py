"""
Bot Gateway Service - Admin Panel Handlers
UK Management Bot

Handlers for admin panel: user management, request management, system config, etc.
"""

import logging
from typing import Optional
from datetime import datetime

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from app.integrations.user_client import UserServiceClient
from app.integrations.request_client import RequestServiceClient
from app.integrations.shift_client import ShiftServiceClient
from app.keyboards import admin as admin_keyboards
from app.keyboards.common import get_main_menu_keyboard, get_cancel_keyboard
from app.states.admin_states import (
    UserManagementStates,
    RequestManagementStates,
    SystemConfigStates,
    BroadcastStates,
    AnalyticsStates,
)

logger = logging.getLogger(__name__)

# Create router
router = Router(name="admin")

# Initialize service clients
user_client = UserServiceClient()
request_client = RequestServiceClient()
shift_client = ShiftServiceClient()


# ===========================================
# Access Control Decorator
# ===========================================


def admin_only(handler):
    """
    Decorator to ensure only admins can access handler.
    """

    async def wrapper(message_or_callback, user_role: str, language: str, **kwargs):
        if user_role not in ["admin", "manager"]:
            texts = {
                "ru": "❌ У вас нет прав для выполнения этой команды.",
                "uz": "❌ Sizda bu buyruqni bajarish uchun huquq yo'q.",
            }
            error_text = texts.get(language, texts["ru"])

            if isinstance(message_or_callback, Message):
                await message_or_callback.answer(error_text)
            else:
                await message_or_callback.message.answer(error_text)
                await message_or_callback.answer()
            return

        return await handler(message_or_callback, user_role=user_role, language=language, **kwargs)

    return wrapper


# ===========================================
# Main Admin Panel
# ===========================================


@router.message(F.text.in_(["👨‍💼 Админ-панель", "👨‍💼 Admin panel"]))
@router.message(Command("admin"))
async def cmd_admin_panel(
    message: Message,
    user_role: str,
    language: str,
    state: FSMContext,
):
    """
    Show main admin panel.

    Available for: admin, manager
    """
    if user_role not in ["admin", "manager"]:
        texts = {
            "ru": "❌ У вас нет доступа к админ-панели.",
            "uz": "❌ Sizda admin panelga kirish huquqi yo'q.",
        }
        await message.answer(texts.get(language, texts["ru"]))
        return

    await state.clear()

    texts = {
        "ru": (
            "👨‍💼 <b>Админ-панель</b>\n\n"
            "Выберите раздел:\n\n"
            "• <b>Пользователи</b> - Управление пользователями\n"
            "• <b>Заявки</b> - Управление заявками\n"
            "• <b>Смены</b> - Управление сменами\n"
            "• <b>Аналитика</b> - Просмотр отчетов\n"
            "• <b>Рассылка</b> - Отправка сообщений\n"
            "• <b>Настройки</b> - Системные настройки\n"
            "• <b>Логи</b> - Просмотр логов системы"
        ),
        "uz": (
            "👨‍💼 <b>Admin panel</b>\n\n"
            "Bo'limni tanlang:\n\n"
            "• <b>Foydalanuvchilar</b> - Foydalanuvchilarni boshqarish\n"
            "• <b>Arizalar</b> - Arizalarni boshqarish\n"
            "• <b>Smenalar</b> - Smenalarni boshqarish\n"
            "• <b>Analitika</b> - Hisobotlarni ko'rish\n"
            "• <b>Xabar yuborish</b> - Xabar yuborish\n"
            "• <b>Sozlamalar</b> - Tizim sozlamalari\n"
            "• <b>Loglar</b> - Tizim loglarini ko'rish"
        ),
    }

    await message.answer(
        text=texts.get(language, texts["ru"]),
        reply_markup=admin_keyboards.get_admin_menu_keyboard(language),
        parse_mode="HTML",
    )


# ===========================================
# User Management
# ===========================================


@router.message(F.text.in_(["👥 Пользователи", "👥 Foydalanuvchilar"]))
@admin_only
async def button_users(
    message: Message,
    user_role: str,
    language: str,
    state: FSMContext,
):
    """
    Show user management menu.
    """
    await state.clear()

    texts = {
        "ru": (
            "👥 <b>Управление пользователями</b>\n\n"
            "Выберите способ поиска пользователей:"
        ),
        "uz": (
            "👥 <b>Foydalanuvchilarni boshqarish</b>\n\n"
            "Foydalanuvchilarni qidirish usulini tanlang:"
        ),
    }

    await message.answer(
        text=texts.get(language, texts["ru"]),
        reply_markup=admin_keyboards.get_user_search_options_keyboard(language),
        parse_mode="HTML",
    )

    await state.set_state(UserManagementStates.waiting_for_search_query)


@router.callback_query(F.data.startswith("user_search:"))
async def callback_user_search(
    callback: CallbackQuery,
    token: str,
    language: str,
    state: FSMContext,
):
    """
    Handle user search option selection.
    """
    await callback.answer()

    search_type = callback.data.split(":")[-1]

    texts = {
        "ru": {
            "phone": "📱 Введите номер телефона пользователя:",
            "name": "👤 Введите имя пользователя:",
            "role": "🏷 Выберите роль:",
            "all": "⏳ Загружаю всех пользователей...",
            "active": "⏳ Загружаю активных пользователей...",
            "blocked": "⏳ Загружаю заблокированных пользователей...",
        },
        "uz": {
            "phone": "📱 Foydalanuvchi telefon raqamini kiriting:",
            "name": "👤 Foydalanuvchi ismini kiriting:",
            "role": "🏷 Rolni tanlang:",
            "all": "⏳ Barcha foydalanuvchilar yuklanmoqda...",
            "active": "⏳ Faol foydalanuvchilar yuklanmoqda...",
            "blocked": "⏳ Bloklangan foydalanuvchilar yuklanmoqda...",
        },
    }

    lang_texts = texts.get(language, texts["ru"])

    if search_type == "role":
        await callback.message.answer(
            lang_texts["role"],
            reply_markup=admin_keyboards.get_role_selection_keyboard(language),
        )
        return

    if search_type in ["all", "active", "blocked"]:
        loading_msg = await callback.message.answer(lang_texts[search_type])

        try:
            # Get users from User Service
            params = {"limit": 10}
            if search_type == "active":
                params["is_active"] = True
            elif search_type == "blocked":
                params["is_active"] = False

            result = await user_client.get_users(token=token, **params)

            await loading_msg.delete()

            users = result.get("items", [])

            if not users:
                await callback.message.answer(
                    "👥 Пользователи не найдены"
                    if language == "ru"
                    else "👥 Foydalanuvchilar topilmadi"
                )
                return

            # Display users with action buttons
            for user in users[:5]:  # Show first 5
                user_id = user.get("id")
                full_name = f"{user.get('first_name', '')} {user.get('last_name', '')}".strip()
                phone = user.get("phone", "N/A")
                role = user.get("role", "N/A")
                is_active = user.get("is_active", True)

                status_emoji = "✅" if is_active else "🚫"

                user_info = (
                    f"{status_emoji} <b>{full_name}</b>\n"
                    f"📱 {phone}\n"
                    f"🏷 Роль: {role}\n"
                    f"🆔 ID: <code>{user_id}</code>"
                )

                await callback.message.answer(
                    user_info,
                    reply_markup=admin_keyboards.get_user_actions_keyboard(
                        user_id, is_active, language
                    ),
                    parse_mode="HTML",
                )

            total = result.get("total", 0)
            if total > 5:
                await callback.message.answer(
                    f"<i>Показаны первые 5 из {total} пользователей</i>"
                    if language == "ru"
                    else f"<i>{total} tadan birinchi 5 ta ko'rsatildi</i>",
                    parse_mode="HTML",
                )

        except Exception as e:
            logger.error(f"Error loading users: {e}")
            await loading_msg.delete()
            await callback.message.answer(
                "❌ Ошибка при загрузке пользователей"
                if language == "ru"
                else "❌ Foydalanuvchilarni yuklashda xatolik"
            )

        return

    # For phone/name search, prompt for input
    await callback.message.answer(lang_texts[search_type])
    await state.update_data(search_type=search_type)


@router.callback_query(F.data.startswith("user:view:"))
async def callback_view_user(
    callback: CallbackQuery,
    token: str,
    language: str,
):
    """
    View detailed user information.
    """
    user_id = callback.data.split(":")[-1]

    try:
        user = await user_client.get_user_by_id(user_id=user_id, token=token)

        full_name = f"{user.get('first_name', '')} {user.get('last_name', '')}".strip()
        phone = user.get("phone", "N/A")
        role = user.get("role", "N/A")
        is_active = user.get("is_active", True)
        created_at = user.get("created_at", "N/A")
        telegram_id = user.get("telegram_id")

        status_text = "✅ Активен" if is_active else "🚫 Заблокирован"
        if language == "uz":
            status_text = "✅ Faol" if is_active else "🚫 Bloklangan"

        response = (
            f"👤 <b>Информация о пользователе</b>\n\n"
            f"<b>Имя:</b> {full_name}\n"
            f"<b>Телефон:</b> {phone}\n"
            f"<b>Роль:</b> {role}\n"
            f"<b>Статус:</b> {status_text}\n"
            f"<b>Telegram ID:</b> <code>{telegram_id}</code>\n"
            f"<b>ID:</b> <code>{user_id}</code>\n"
            f"<b>Дата регистрации:</b> {created_at[:10] if created_at != 'N/A' else 'N/A'}"
        )

        await callback.message.answer(response, parse_mode="HTML")
        await callback.answer()

    except Exception as e:
        logger.error(f"Error viewing user: {e}")
        await callback.message.answer(
            "❌ Ошибка при загрузке данных пользователя"
            if language == "ru"
            else "❌ Foydalanuvchi ma'lumotlarini yuklashda xatolik"
        )
        await callback.answer()


@router.callback_query(F.data.startswith("user:role:"))
async def callback_change_role(
    callback: CallbackQuery,
    language: str,
    state: FSMContext,
):
    """
    Initiate role change for user.
    """
    user_id = callback.data.split(":")[-1]

    texts = {
        "ru": "🏷 Выберите новую роль для пользователя:",
        "uz": "🏷 Foydalanuvchi uchun yangi rolni tanlang:",
    }

    await callback.message.answer(
        texts.get(language, texts["ru"]),
        reply_markup=admin_keyboards.get_role_selection_keyboard(language),
    )

    await state.update_data(user_id=user_id, action="change_role")
    await state.set_state(UserManagementStates.waiting_for_role_change)

    await callback.answer()


@router.callback_query(F.data.startswith("role:"), UserManagementStates.waiting_for_role_change)
async def callback_confirm_role_change(
    callback: CallbackQuery,
    token: str,
    language: str,
    state: FSMContext,
):
    """
    Confirm and apply role change.
    """
    new_role = callback.data.split(":")[-1]
    data = await state.get_data()
    user_id = data.get("user_id")

    texts = {
        "ru": {
            "processing": "⏳ Обновляю роль...",
            "success": f"✅ Роль успешно изменена на: {new_role}",
            "error": "❌ Не удалось изменить роль",
        },
        "uz": {
            "processing": "⏳ Rol yangilanmoqda...",
            "success": f"✅ Rol muvaffaqiyatli o'zgartirildi: {new_role}",
            "error": "❌ Rolni o'zgartirishda xatolik",
        },
    }

    lang_texts = texts.get(language, texts["ru"])

    await callback.answer(lang_texts["processing"])

    try:
        result = await user_client.update_user(
            user_id=user_id, data={"role": new_role}, token=token
        )

        await callback.message.answer(lang_texts["success"])
        await state.clear()

    except Exception as e:
        logger.error(f"Error changing user role: {e}")
        await callback.message.answer(lang_texts["error"])
        await state.clear()


@router.callback_query(F.data.startswith("user:block:"))
async def callback_block_user(
    callback: CallbackQuery,
    token: str,
    language: str,
):
    """
    Block user.
    """
    user_id = callback.data.split(":")[-1]

    texts = {
        "ru": {
            "processing": "⏳ Блокирую пользователя...",
            "success": "✅ Пользователь заблокирован",
            "error": "❌ Не удалось заблокировать пользователя",
        },
        "uz": {
            "processing": "⏳ Foydalanuvchi bloklanmoqda...",
            "success": "✅ Foydalanuvchi bloklandi",
            "error": "❌ Foydalanuvchini bloklashda xatolik",
        },
    }

    lang_texts = texts.get(language, texts["ru"])

    await callback.answer(lang_texts["processing"])

    try:
        result = await user_client.update_user(
            user_id=user_id, data={"is_active": False}, token=token
        )

        await callback.message.answer(lang_texts["success"])

    except Exception as e:
        logger.error(f"Error blocking user: {e}")
        await callback.message.answer(lang_texts["error"])


@router.callback_query(F.data.startswith("user:unblock:"))
async def callback_unblock_user(
    callback: CallbackQuery,
    token: str,
    language: str,
):
    """
    Unblock user.
    """
    user_id = callback.data.split(":")[-1]

    texts = {
        "ru": {
            "processing": "⏳ Разблокирую пользователя...",
            "success": "✅ Пользователь разблокирован",
            "error": "❌ Не удалось разблокировать пользователя",
        },
        "uz": {
            "processing": "⏳ Foydalanuvchi blokdan chiqarilmoqda...",
            "success": "✅ Foydalanuvchi blokdan chiqarildi",
            "error": "❌ Foydalanuvchini blokdan chiqarishda xatolik",
        },
    }

    lang_texts = texts.get(language, texts["ru"])

    await callback.answer(lang_texts["processing"])

    try:
        result = await user_client.update_user(
            user_id=user_id, data={"is_active": True}, token=token
        )

        await callback.message.answer(lang_texts["success"])

    except Exception as e:
        logger.error(f"Error unblocking user: {e}")
        await callback.message.answer(lang_texts["error"])


# ===========================================
# Request Management (Admin)
# ===========================================


@router.message(F.text.in_(["📋 Заявки", "📋 Arizalar"]))
@admin_only
async def button_requests_admin(
    message: Message,
    user_role: str,
    language: str,
    state: FSMContext,
):
    """
    Show admin request management menu.
    """
    await state.clear()

    texts = {
        "ru": (
            "📋 <b>Управление заявками</b>\n\n"
            "Выберите способ поиска заявок:"
        ),
        "uz": (
            "📋 <b>Arizalarni boshqarish</b>\n\n"
            "Arizalarni qidirish usulini tanlang:"
        ),
    }

    await message.answer(
        text=texts.get(language, texts["ru"]),
        reply_markup=admin_keyboards.get_request_search_options_keyboard(language),
        parse_mode="HTML",
    )

    await state.set_state(RequestManagementStates.waiting_for_search_query)


@router.callback_query(F.data.startswith("req_search:"))
async def callback_request_search(
    callback: CallbackQuery,
    token: str,
    language: str,
    state: FSMContext,
):
    """
    Handle request search option selection.
    """
    await callback.answer()

    search_type = callback.data.split(":")[-1]

    if search_type == "all":
        loading_msg = await callback.message.answer(
            "⏳ Загружаю заявки..." if language == "ru" else "⏳ Arizalar yuklanmoqda..."
        )

        try:
            result = await request_client.get_all_requests(token=token, limit=10)

            await loading_msg.delete()

            requests = result.get("items", [])

            if not requests:
                await callback.message.answer(
                    "📋 Заявки не найдены" if language == "ru" else "📋 Arizalar topilmadi"
                )
                return

            for req in requests[:5]:
                request_number = req.get("request_number")
                status = req.get("status")
                building = req.get("building")
                apartment = req.get("apartment")
                description = req.get("description", "")[:50]

                req_info = (
                    f"📋 <b>Заявка {request_number}</b>\n"
                    f"📊 Статус: {status}\n"
                    f"🏢 Дом: {building}, кв. {apartment}\n"
                    f"📝 {description}..."
                )

                await callback.message.answer(
                    req_info,
                    reply_markup=admin_keyboards.get_request_admin_actions_keyboard(
                        request_number, status, language
                    ),
                    parse_mode="HTML",
                )

            total = result.get("total", 0)
            if total > 5:
                await callback.message.answer(
                    f"<i>Показаны первые 5 из {total} заявок</i>"
                    if language == "ru"
                    else f"<i>{total} tadan birinchi 5 ta ko'rsatildi</i>",
                    parse_mode="HTML",
                )

        except Exception as e:
            logger.error(f"Error loading requests: {e}")
            await loading_msg.delete()
            await callback.message.answer(
                "❌ Ошибка при загрузке заявок"
                if language == "ru"
                else "❌ Arizalarni yuklashda xatolik"
            )


# ===========================================
# Analytics
# ===========================================


@router.message(F.text.in_(["📊 Аналитика", "📊 Analitika"]))
@admin_only
async def button_analytics(
    message: Message,
    user_role: str,
    language: str,
    state: FSMContext,
):
    """
    Show analytics menu.
    """
    await state.clear()

    texts = {
        "ru": "📊 <b>Аналитика</b>\n\nВыберите тип отчета:",
        "uz": "📊 <b>Analitika</b>\n\nHisobot turini tanlang:",
    }

    await message.answer(
        text=texts.get(language, texts["ru"]),
        reply_markup=admin_keyboards.get_analytics_reports_keyboard(language),
        parse_mode="HTML",
    )


# ===========================================
# Broadcast Messages
# ===========================================


@router.message(F.text.in_(["📢 Рассылка", "📢 Xabar yuborish"]))
@admin_only
async def button_broadcast(
    message: Message,
    user_role: str,
    language: str,
    state: FSMContext,
):
    """
    Show broadcast menu.
    """
    await state.clear()

    texts = {
        "ru": (
            "📢 <b>Рассылка сообщений</b>\n\n"
            "Выберите целевую аудиторию для рассылки:"
        ),
        "uz": (
            "📢 <b>Xabar yuborish</b>\n\n"
            "Xabar yuborish uchun maqsadli auditoriyani tanlang:"
        ),
    }

    await message.answer(
        text=texts.get(language, texts["ru"]),
        reply_markup=admin_keyboards.get_broadcast_target_keyboard(language),
        parse_mode="HTML",
    )

    await state.set_state(BroadcastStates.waiting_for_target_selection)


# ===========================================
# System Configuration
# ===========================================


@router.message(F.text.in_(["⚙️ Настройки", "⚙️ Sozlamalar"]))
@admin_only
async def button_config(
    message: Message,
    user_role: str,
    language: str,
    state: FSMContext,
):
    """
    Show system configuration menu.
    """
    await state.clear()

    texts = {
        "ru": "⚙️ <b>Системные настройки</b>\n\nВыберите категорию:",
        "uz": "⚙️ <b>Tizim sozlamalari</b>\n\nKategoriyani tanlang:",
    }

    await message.answer(
        text=texts.get(language, texts["ru"]),
        reply_markup=admin_keyboards.get_config_categories_keyboard(language),
        parse_mode="HTML",
    )


# ===========================================
# Logs Viewer
# ===========================================


@router.message(F.text.in_(["📝 Логи", "📝 Loglar"]))
@admin_only
async def button_logs(
    message: Message,
    user_role: str,
    language: str,
):
    """
    Show system logs (placeholder).
    """
    texts = {
        "ru": (
            "📝 <b>Системные логи</b>\n\n"
            "Функция просмотра логов будет доступна в следующей версии.\n\n"
            "Для просмотра логов используйте команду:\n"
            "<code>docker-compose logs -f bot-gateway</code>"
        ),
        "uz": (
            "📝 <b>Tizim loglari</b>\n\n"
            "Loglarni ko'rish funksiyasi keyingi versiyada mavjud bo'ladi.\n\n"
            "Loglarni ko'rish uchun buyruqdan foydalaning:\n"
            "<code>docker-compose logs -f bot-gateway</code>"
        ),
    }

    await message.answer(texts.get(language, texts["ru"]), parse_mode="HTML")
