"""Роутер бота лифтёра с гейтом уровня роутера (Ф5, T10).

ActionGate — root-фильтр (идиома волн A/D, см. ``handlers/_role_gate.py``): без
действия ``elevators.technician`` (состав ролей — ``authz/catalog.py``) апдейт
роутер не берёт и уходит дальше по цепочке. Специализацию «лифты» гейт не знает —
её проверяет каждый sync-юнит (``_units.check_access``), поэтому менеджер без роли
executor доходит до хендлера и получает внятный отказ вместо тишины.
"""

from aiogram import Router

from uk_management_bot.handlers._role_gate import ActionGate

router = Router(name="elevators")
router.message.filter(ActionGate("elevators.technician"))
router.callback_query.filter(ActionGate("elevators.technician"))
