from aiogram import Router

from uk_management_bot.handlers._role_gate import ActionGate

router = Router()
# Гейт всего пакета address_apartments (шесть подмодулей на одном роутере):
# root-фильтр отрабатывает ДО хендлеров, отказ = UNHANDLED — транзит цел.
router.callback_query.filter(ActionGate("admin_panel.use"))
router.message.filter(ActionGate("admin_panel.use"))
