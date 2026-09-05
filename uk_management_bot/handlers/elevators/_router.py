"""Роутер бота лифтёра с ролевым гейтом уровня роутера (Ф5, T10).

RoleGate — root-фильтр (идиома волн A/D, см. ``handlers/_role_gate.py``): без
роли из ``TECHNICIAN_GATE_ROLES`` апдейт роутер не берёт и уходит дальше по
цепочке. Специализацию «лифты» гейт не знает — её проверяет каждый sync-юнит
(``_units.check_access``), поэтому менеджер без роли executor доходит до
хендлера и получает внятный отказ вместо тишины.
"""

from aiogram import Router

from uk_management_bot.handlers._role_gate import RoleGate

TECHNICIAN_GATE_ROLES: tuple[str, ...] = ("executor", "manager", "admin")

router = Router(name="elevators")
router.message.filter(RoleGate(TECHNICIAN_GATE_ROLES))
router.callback_query.filter(RoleGate(TECHNICIAN_GATE_ROLES))
