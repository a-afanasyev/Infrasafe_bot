from aiogram import Router

from uk_management_bot.handlers._role_gate import RoleGate

router = Router()
# D1: один гейт на весь менеджерский пакет смен (71 хендлер). Исполнительский
# интерфейс живёт в handlers/my_shifts/ — пересечения callback-пространств нет.
# ⚠️ auto_manager.py переиспользует back_to_shifts из schedule.py — для
# менеджера гейт прозрачен (пиннится тестом).
router.callback_query.filter(RoleGate())
router.message.filter(RoleGate())
