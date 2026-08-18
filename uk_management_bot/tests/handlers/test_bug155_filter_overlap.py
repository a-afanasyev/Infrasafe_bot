"""BUG-155 п.3: три перекрытия фильтров — апдейт съедает не тот хендлер.

Класс дефектов, который не виден ни в одном юнит-тесте хендлера: сам хендлер
корректен, но до него не доходит апдейт. Решает ПОРЯДОК регистрации роутеров
(`main.py`) и широта фильтра — «первый подошедший забирает».

Три живых случая:

1. `user_management/panels.handle_view_user_from_notification` с фильтром
   `startswith("view_user_")` съедает `view_user_documents_{id}`, адресованный
   `user_verification/documents.view_user_documents`: user_management включён
   раньше (`main.py:397` против `:399`). Разбор `int("documents")` падает, и
   менеджер вместо списка документов получает «ошибка обработки запроса».
2. `request_comments.handle_view_comments` с фильтром `startswith("view_comments_")`
   съедает `view_comments_by_type_{type}_{number}` — оба в ОДНОМ роутере,
   выигрывает зарегистрированный выше. Выборка по типу недостижима: менеджер
   всегда видит всю историю.
3. `address_moderation.cancel_moderation_action` с голым `F.data == "cancel_action"`
   съедает «Отмену» ЧУЖИХ флоу: роутер включён первым из адресных
   (`main.py:391`). Кнопка живёт только внутри FSM-состояний модерации и дворов
   (`get_cancel_keyboard_inline` — единственный генератор), поэтому отмена
   создания двора очищала состояние и показывала список МОДЕРАЦИИ.

Тесты проверяют РАЗРЕШЕНИЕ роутинга на настоящих роутерах в порядке `main.py`,
а не поведение хендлеров: дефект именно в разрешении. Лечение — по прецеденту
PR-25/BUG-BOT-034: строгий регекс на `REQUEST_NUMBER_CORE` вместо открытого
`startswith`, и фильтр по собственному состоянию вместо голого равенства.
"""
from __future__ import annotations

from uk_management_bot.tests.handlers.routing_probe import resolve
from uk_management_bot.handlers.user_management import router as user_management_router
from uk_management_bot.handlers.user_verification import router as user_verification_router
from uk_management_bot.handlers.request_comments import router as request_comments_router
from uk_management_bot.handlers.address_moderation import router as address_moderation_router
from uk_management_bot.handlers.address_apartments import router as address_apartments_router
from uk_management_bot.handlers.address_buildings import router as address_buildings_router
from uk_management_bot.handlers.address_yards import router as address_yards_router


# Порядок — как в main.py; именно он и определяет победителя.
USER_ROUTERS = [user_management_router, user_verification_router]
ADDRESS_ROUTERS = [
    address_moderation_router,
    address_apartments_router,
    address_buildings_router,
    address_yards_router,
    user_management_router,
]


# ══════════════════════════════════════════════════════════════════════════════
# 1. view_user_ vs view_user_documents_
# ══════════════════════════════════════════════════════════════════════════════

def test_documents_callback_reaches_documents_handler():
    assert resolve(USER_ROUTERS, "view_user_documents_5") == "view_user_documents"


def test_plain_view_user_still_reaches_its_handler():
    assert resolve(USER_ROUTERS, "view_user_5") == "handle_view_user_from_notification"


def test_view_user_filter_is_not_open_set():
    """Любой будущий `view_user_<слово>_<id>` не должен проваливаться сюда."""
    assert resolve(USER_ROUTERS, "view_user_profile_5") != "handle_view_user_from_notification"


# ══════════════════════════════════════════════════════════════════════════════
# 2. view_comments_ vs view_comments_by_type_
# ══════════════════════════════════════════════════════════════════════════════

def test_comments_by_type_reaches_its_handler():
    assert resolve(
        [request_comments_router], "view_comments_by_type_clarification_260818-001"
    ) == "handle_view_comments_by_type"


def test_plain_view_comments_still_reaches_its_handler():
    assert resolve([request_comments_router], "view_comments_260818-001") == "handle_view_comments"


def test_back_to_comments_untouched():
    assert resolve([request_comments_router], "back_to_comments_260818-001") == "handle_back_to_comments"


# ══════════════════════════════════════════════════════════════════════════════
# 3. cancel_action — каждый флоу отменяет СВОЁ
# ══════════════════════════════════════════════════════════════════════════════

def test_cancel_in_yard_flow_reaches_yards_handler():
    """Отмена создания двора не должна уводить в список модерации."""
    assert resolve(
        ADDRESS_ROUTERS, "cancel_action",
        raw_state="YardManagementStates:waiting_for_yard_name",
    ) == "cancel_action"


def test_cancel_in_moderation_flow_reaches_moderation_handler():
    assert resolve(
        ADDRESS_ROUTERS, "cancel_action",
        raw_state="ApartmentModerationStates:waiting_for_approval_comment",
    ) == "cancel_moderation_action"


def test_cancel_in_rejection_flow_reaches_moderation_handler():
    assert resolve(
        ADDRESS_ROUTERS, "cancel_action",
        raw_state="ApartmentModerationStates:waiting_for_rejection_comment",
    ) == "cancel_moderation_action"


def test_stateless_cancel_still_handled():
    """Без состояния кнопка обязана остаться обработанной, а не «проглотиться».

    Молчаливый клик хуже неверного экрана: человек не понимает, нажалось ли.
    """
    assert resolve(ADDRESS_ROUTERS, "cancel_action", raw_state=None) is not None
