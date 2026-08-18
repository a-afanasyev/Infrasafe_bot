"""Ролевой гейт уровня роутера + deny-роутер адресного callback-пространства.

Механика (проверена по aiogram `dispatcher/router.py`, `_propagate_event`):
`observer.check_root_filters(event, **kwargs)` вызывается ДО перебора хендлеров
и ДО обхода `sub_routers`; `kwargs` — data глобальных update-middleware
(`dp.update.middleware`, main.py), то есть `roles`/`user` уже лежат там. Отказ
root-фильтра возвращает `UNHANDLED`, и апдейт идёт к СЛЕДУЮЩЕМУ роутеру цепочки —
транзит чужих апдейтов (clarification_replies, feedback, access_control, base)
гейт не ломает. Поэтому `.filter()`, а не `outer_middleware`.

Кому ставится: четыре адресных роутера (yards/buildings/moderation/apartments)
и пакет `shift_management`. Роутеры смешанного назначения (`user_apartments`,
`shifts`) гейтом НЕ закрываются — там точечные `@require_role`/ownership.
"""
from __future__ import annotations

import re
from typing import List, Optional

from aiogram import F, Router
from aiogram.filters import Filter
from aiogram.types import CallbackQuery, TelegramObject

from uk_management_bot.utils.auth_helpers import parse_roles_safe
from uk_management_bot.utils.helpers import get_text

DEFAULT_ADMIN_ROLES = ("admin", "manager")


class RoleGate(Filter):
    """Root-фильтр «у пользователя есть роль из allowed_roles».

    Семантика тождественна `has_admin_access` (`utils/auth_helpers.py`) — тому же
    предикату, что у 83 сайтов `@require_role`: сначала `roles` из middleware,
    затем fallback на `parse_roles_safe(user.roles)`. Тождество пиннится тестом
    (test_role_gate.py). Список ролей — явный параметр, чтобы расширение было
    правкой одной строки в месте установки гейта, а не археологией по слоям.

    Fail-closed: `role_mode_middleware` без пользователя кладёт
    `roles=["applicant"]`; нет даже этого (roles=None и user=None) → отказ.

    ⚠️ `system_admin` НЕ входит осознанно — тождество с `has_admin_access`
    (роль каноническая, но админ-контур бота её никогда не пропускал; на обоих
    продах она встречается только в паре с manager/admin). Расширение — решение
    владельца по всему админ-контуру сразу, отдельный пункт бэклога.
    """

    def __init__(self, allowed_roles: tuple = DEFAULT_ADMIN_ROLES):
        self.allowed_roles = tuple(allowed_roles)

    async def __call__(
        self,
        event: TelegramObject,
        roles: Optional[List[str]] = None,
        user=None,
        **kwargs,
    ) -> bool:
        if roles and any(role in self.allowed_roles for role in roles):
            return True
        if user is not None:
            user_roles = parse_roles_safe(getattr(user, "roles", None))
            if any(role in self.allowed_roles for role in user_roles):
                return True
        return False


# ══════════════════════════════════════════════════════════════════════════════
# Callback-пространство адресного кластера (SSOT для deny-роутера и ратчета R1)
# ══════════════════════════════════════════════════════════════════════════════
#
# Инвентарь на baseline e2a62509: 47 callback-хендлеров кластера, 40 литералов
# с префиксом `addr_` и пять НЕ-`addr_`: `admin_menu`, `cancel_action`,
# `cancel_apartment_selection`, `apartment_create_building:`,
# `building_create_yard:`. Решение по каждому:
#
#   * `addr_*` (кроме `addr_page*`) → deny. `addr_page:`/`addr_page_noop` —
#     ЖИТЕЛЬСКИЙ пагинатор создания заявки (requests/create.py:240,264, роутер
#     включён РАНЬШЕ адресных); просроченная кнопка вне состояния должна молчать,
#     а не пугать жителя «нет прав». `addr:` (create.py:188) под `^addr_` не
#     подпадает по построению.
#   * `admin_menu`, `apartment_create_building:`, `building_create_yard:` → deny
#     (других хендлеров этих литералов в боте нет — без deny апдейт жителя
#     умер бы молча).
#   * `cancel_action` → НЕ deny: транзитом доходит до
#     user_management/actions.py (has_admin_access → errors.permission_denied) —
#     штатный последний рубеж, пиннится тестом A5.
#   * `cancel_apartment_selection` → НЕ deny: после A3 это жительский callback,
#     хендлер в user_apartment_selection.py (роутер РАНЬШЕ адресных).
ADDRESS_CALLBACK_RE = re.compile(
    r"^(?:"
    r"addr_(?!page)"
    r"|admin_menu$"
    r"|apartment_create_building:"
    r"|building_create_yard:"
    r")"
)

deny_router = Router(name="address_deny")


@deny_router.callback_query(F.data.regexp(ADDRESS_CALLBACK_RE))
async def deny_address_callback(callback: CallbackQuery, language: str = "ru"):
    """Внятный отказ вместо тишины: сюда доходят только апдейты, которые
    гейтованные адресные роутеры пропустили (root-фильтр вернул UNHANDLED),
    т.е. апдейты пользователей без admin|manager."""
    await callback.answer(get_text("auth.no_access", language=language), show_alert=True)


class ShiftPackageWouldHandle(Filter):
    """«Этот апдейт взял бы пакет shift_management, если бы не RoleGate».

    Deny-фолбэк для D1: до гейта 62 из 71 хендлеров пакета несли собственный
    `@require_role` и ЯВНО отвечали «нет прав»; root-фильтр превратил бы этот
    отказ в тишину (у callback виснет спиннер, /shifts молчит). Вместо ручного
    инвентаря литералов пакета фильтр прогоняет апдейт по хендлерам самого
    гейтованного роутера (без его root-фильтров) — SSOT по построению: новый
    хендлер пакета покрывается автоматически. Сюда доходят только апдейты,
    которые не взял никто выше по цепочке — цена O(handlers) платится редко.

    Импорт роутера ленивый: _role_gate импортируется самим пакетом.
    """

    async def __call__(self, event: TelegramObject, raw_state=None, **kwargs) -> bool:
        from uk_management_bot.handlers.shift_management import router as shift_router

        observer = (shift_router.callback_query
                    if isinstance(event, CallbackQuery) else shift_router.message)
        for handler in observer.handlers:
            ok, _ = await handler.check(event, raw_state=raw_state, **kwargs)
            if ok:
                return True
        return False


@deny_router.callback_query(ShiftPackageWouldHandle())
async def deny_shift_callback(callback: CallbackQuery, language: str = "ru"):
    await callback.answer(get_text("auth.no_access", language=language), show_alert=True)


@deny_router.message(ShiftPackageWouldHandle())
async def deny_shift_message(message, language: str = "ru"):
    await message.answer(get_text("auth.no_access", language=language))
