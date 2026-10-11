from aiogram import Router

from uk_management_bot.handlers._role_gate import ActionGate

router = Router()
# D1: один гейт на весь менеджерский пакет смен (71 хендлер). Исполнительский
# интерфейс живёт в handlers/my_shifts/ — пересечения callback-пространств нет.
# ⚠️ auto_manager.py переиспользует back_to_shifts из schedule.py — для
# менеджера гейт прозрачен (пиннится тестом).
router.callback_query.filter(ActionGate("admin_panel.use"))
router.message.filter(ActionGate("admin_panel.use"))
