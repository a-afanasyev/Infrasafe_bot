from aiogram import Router

from uk_management_bot.handlers._role_gate import RoleGate

router = Router()
# Гейт всего пакета address_apartments (шесть подмодулей на одном роутере):
# root-фильтр отрабатывает ДО хендлеров, отказ = UNHANDLED — транзит цел.
router.callback_query.filter(RoleGate())
router.message.filter(RoleGate())
