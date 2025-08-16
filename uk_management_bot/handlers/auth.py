from aiogram import Router, F
from aiogram.types import Message
from sqlalchemy.orm import Session

from services.auth_service import AuthService
from keyboards.base import get_main_keyboard, get_cancel_keyboard

router = Router()


@router.message(F.text == "🔑 Войти")
async def login_via_button(message: Message, db: Session):
    auth = AuthService(db)
    user = await auth.get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        last_name=message.from_user.last_name,
    )
    if user.status == "approved":
        await message.answer("Вы уже авторизованы.", reply_markup=get_main_keyboard())
        return
    ok = await auth.approve_user(message.from_user.id, role="applicant")
    if ok:
        await message.answer(
            "✅ Авторизация выполнена. Вы вошли как заявитель.",
            reply_markup=get_main_keyboard(),
        )
    else:
        await message.answer(
            "Не удалось выполнить авторизацию. Попробуйте позже или обратитесь к менеджеру.",
            reply_markup=get_cancel_keyboard(),
        )


@router.message(F.text == "/login")
async def login_command(message: Message, db: Session):
    # Аналог кнопки — одобряем пользователя как заявителя
    await login_via_button(message, db)


