"""Развилка первого входа: «Я житель» или «Я сотрудник (по приглашению)».

Зачем: ссылка-приглашение сотрудника — статический ``https://t.me/<бот>`` без
параметров, роль едет отдельным 246-символьным токеном (в deep-link он не
помещается: Telegram даёт 64 символа из ``[A-Za-z0-9_-]``). Человек жмёт
«Начать», попадает в обычный /start и молча регистрируется ЖИТЕЛЕМ. Развилка
задаёт вопрос до того, как он уйдёт не туда.

Ветка жителя ведёт в существующий онбординг (``base.send_onboarding_screen``),
ветка сотрудника — в существующую анкету инвайта
(``auth.start_invite_registration``). Своей логики регистрации здесь нет.

AUD3-07/AUD5-ARCH-1: DB-фазы в этом модуле нет вовсе — вся работа с сессией
живёт в вызываемых функциях, которые уже под ``run_db``; наружу пробрасывается
только seam ``_db``.
"""
import logging
import re

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove

from uk_management_bot.handlers.auth import start_invite_registration
from uk_management_bot.handlers.base import send_onboarding_screen  # noqa: F401 — реэкспорт для тестов/колбэков
from uk_management_bot.keyboards.base import get_no_invite_token_inline
from uk_management_bot.keyboards.contact import get_share_contact_keyboard
from uk_management_bot.states.registration import RegistrationStates
from uk_management_bot.utils.button_texts import get_back_texts, get_cancel_texts
from uk_management_bot.utils.helpers import get_text

logger = logging.getLogger(__name__)
router = Router(name="start_role_choice")

CANCEL_TEXTS = get_cancel_texts()
BACK_TEXTS = get_back_texts()

# Токен: invite_v1:<payload base64url>.<64 hex подписи>. Ищем ПОДСТРОКОЙ в любом
# месте сообщения — иначе отвалятся реальные способы прислать код: командой
# /join, в бэктиках (ровно так его печатает инструкция менеджеру), форвардом
# всего сообщения целиком, с переносами строк от мобильной вставки.
_TOKEN_RE = re.compile(r"invite_v1:([A-Za-z0-9_-]+)\.([0-9a-fA-F]{64})", re.IGNORECASE)


def extract_invite_token(text) -> str | None:
    """Достать инвайт-токен из произвольного текста. -> канонический вид|None.

    Префикс матчится регистронезависимо (автокапитализация на iOS), но в ответ
    отдаётся канонический ``invite_v1:`` — payload регистрозависим, его не
    трогаем.
    """
    if not text:
        return None
    match = _TOKEN_RE.search(text)
    if not match:
        return None
    return f"invite_v1:{match.group(1)}.{match.group(2)}"


@router.callback_query(F.data == "start_role:resident")
async def choose_resident(callback: CallbackQuery, state: FSMContext, language: str = "ru", *, _db=None):
    """«Я житель» → сегодняшний онбординг, без изменений."""
    await state.clear()
    await _strip_markup(callback)
    await send_onboarding_screen(callback.message, callback.from_user, language, _db=_db)
    await callback.answer()
    logger.info(f"Пользователь {callback.from_user.id} выбрал ветку жителя")


@router.callback_query(F.data == "start_role:employee")
async def choose_employee(callback: CallbackQuery, state: FSMContext, language: str = "ru"):
    """«Я сотрудник» → просим прислать код приглашения.

    Лимитер здесь НЕ трогаем: он считает каждую проверку (3 попытки на 600 c),
    и потратить их на нажатие кнопки — значит запереть человека до того, как он
    вообще прислал код.
    """
    await state.set_state(RegistrationStates.waiting_for_employee_contact)
    await _strip_markup(callback)
    await callback.message.answer(
        get_text("start_role.employee_contact_prompt", language=language),
        reply_markup=get_share_contact_keyboard(language, with_cancel=True),
    )
    await callback.answer()
    logger.info(f"Пользователь {callback.from_user.id} выбрал ветку сотрудника")


@router.message(StateFilter(RegistrationStates.waiting_for_employee_contact), F.contact)
async def employee_contact(message: Message, state: FSMContext, language: str = "ru"):
    """Контакт сотрудника ДО токена (спека §3.4). В БД не пишем — иначе
    бросивший анкету не увидит развилку на следующем /start."""
    if message.contact.user_id != message.from_user.id:
        await message.answer(get_text("phone_request_flow.foreign_contact", language=language))
        return
    phone = message.contact.phone_number
    if not phone.startswith("+"):
        phone = "+" + phone
    await state.update_data(employee_phone=phone)
    await state.set_state(RegistrationStates.waiting_for_invite_token)
    await message.answer(
        get_text("start_role.token_prompt", language=language),
        reply_markup=get_no_invite_token_inline(language),
    )


@router.message(StateFilter(RegistrationStates.waiting_for_employee_contact))
async def employee_contact_text(message: Message, state: FSMContext, language: str = "ru"):
    """Всё, что не контакт, в этом состоянии: отмена или напоминание нажать кнопку.
    Обрабатывается здесь — этот роутер в main.py раньше onboarding/auth."""
    text = (message.text or "").strip()
    if text in CANCEL_TEXTS or text in BACK_TEXTS or text.startswith("/"):
        await state.clear()
        await message.answer(
            get_text("auth.registration_cancelled", language=language),
            reply_markup=ReplyKeyboardRemove(),
        )
        return
    await message.answer(get_text("start_role.employee_contact_required", language=language))


@router.callback_query(F.data == "start_role:no_token")
async def no_invite_token(callback: CallbackQuery, state: FSMContext, language: str = "ru", *, _db=None):
    """«У меня нет кода» → выход из ожидания токена обратно к жителю."""
    await state.clear()
    await _strip_markup(callback)
    await callback.message.answer(get_text("start_role.no_token_hint", language=language))
    await send_onboarding_screen(callback.message, callback.from_user, language, _db=_db)
    await callback.answer()


@router.message(RegistrationStates.waiting_for_invite_token, F.text)
async def receive_invite_token(message: Message, state: FSMContext, language: str = "ru", *, _db=None):
    """Приём кода приглашения сообщением.

    Токен в логи не пишем ни целиком, ни префиксом (SEC-08).
    """
    text = message.text or ""
    token = extract_invite_token(text)

    if token is None:
        # Выходы из состояния: без них человек заперт — хендлер съедает любой
        # текст, включая кнопки главного меню.
        if text.strip() in CANCEL_TEXTS or text.strip() in BACK_TEXTS or text.startswith("/"):
            await state.clear()
            await message.answer(get_text("start_role.no_token_hint", language=language))
            return

        await message.answer(get_text("start_role.token_not_recognized", language=language))
        return

    verdict, _role = await start_invite_registration(
        message, state, token, language=language, staff_only=True, _db=_db
    )

    if verdict in ("already_registered", "registration_pending", "applicant_token"):
        # Повтор не поможет: аккаунт уже заведён, либо код не даёт роль сотрудника.
        await state.clear()
        if verdict == "applicant_token":
            await send_onboarding_screen(message, message.from_user, language, _db=_db)
        return

    # invalid / rate_limited / error — причина уже отправлена, остаёмся в
    # состоянии: опечатка при вставке кода не должна стоить прохода заново.


@router.message(RegistrationStates.waiting_for_invite_token)
async def reject_non_text_token(message: Message, language: str = "ru"):
    """Код прислали не текстом (скриншот приглашения — самый частый случай).

    Без этого хендлера апдейт молча уходил бы в никуда: состояние ожидания
    токена не ловит никто другой, и человек не понимал бы, почему бот молчит.
    """
    await message.answer(get_text("start_role.token_expect_text", language=language))


async def _strip_markup(callback: CallbackQuery) -> None:
    """Снять инлайн-кнопки, чтобы по экрану нельзя было ответить дважды."""
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception as e:
        # Сообщение могло быть уже отредактировано или слишком старым —
        # для основного сценария это неважно.
        logger.debug(f"Не удалось снять разметку выбора роли: {e}")
