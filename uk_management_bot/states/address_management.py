"""
FSM состояния для управления справочником адресов

Определяет состояния для:
- Создания и редактирования дворов
- Создания и редактирования зданий
- Создания и редактирования квартир
- Модерации заявок на квартиры
"""

from aiogram.fsm.state import State, StatesGroup


class YardManagementStates(StatesGroup):
    """FSM состояния для управления дворами"""

    # ═══ СОЗДАНИЕ ДВОРА ═══

    waiting_for_yard_name = State()
    """Ожидание названия двора"""

    waiting_for_yard_description = State()
    """Ожидание описания двора (опционально)"""

    waiting_for_yard_gps = State()
    """Ожидание GPS координат двора (опционально)"""

    # ═══ РЕДАКТИРОВАНИЕ ДВОРА ═══

    waiting_for_new_yard_name = State()
    """Ожидание нового названия двора"""

    waiting_for_new_yard_description = State()
    """Ожидание нового описания двора"""

    waiting_for_new_yard_gps = State()
    """Ожидание новых GPS координат"""


class BuildingManagementStates(StatesGroup):
    """FSM состояния для управления зданиями"""

    # ═══ СОЗДАНИЕ ЗДАНИЯ ═══

    waiting_for_yard_selection = State()
    """Ожидание выбора двора для нового здания"""

    waiting_for_building_address = State()
    """Ожидание адреса здания"""

    waiting_for_building_gps = State()
    """Ожидание GPS координат здания (опционально)"""

    waiting_for_entrance_count = State()
    """Ожидание количества подъездов"""

    waiting_for_floor_count = State()
    """Ожидание количества этажей"""

    waiting_for_building_description = State()
    """Ожидание описания здания (опционально)"""

    # ═══ РЕДАКТИРОВАНИЕ ЗДАНИЯ ═══

    waiting_for_new_building_address = State()
    """Ожидание нового адреса здания"""

    waiting_for_new_yard_selection = State()
    """Ожидание выбора нового двора"""

    waiting_for_new_building_gps = State()
    """Ожидание новых GPS координат"""

    waiting_for_new_entrance_count = State()
    """Ожидание нового количества подъездов"""

    waiting_for_new_floor_count = State()
    """Ожидание нового количества этажей"""

    waiting_for_new_building_description = State()
    """Ожидание нового описания здания"""


class ApartmentManagementStates(StatesGroup):
    """FSM состояния для управления квартирами"""

    # ═══ СОЗДАНИЕ КВАРТИРЫ ═══

    waiting_for_building_selection = State()
    """Ожидание выбора здания для новой квартиры"""

    waiting_for_apartment_number = State()
    """Ожидание номера квартиры"""

    waiting_for_entrance_number = State()
    """Ожидание номера подъезда (опционально)"""

    waiting_for_floor_number = State()
    """Ожидание номера этажа (опционально)"""

    waiting_for_rooms_count = State()
    """Ожидание количества комнат (опционально)"""

    waiting_for_area = State()
    """Ожидание площади квартиры в кв.м (опционально)"""

    waiting_for_apartment_description = State()
    """Ожидание описания квартиры (опционально)"""

    # ═══ РЕДАКТИРОВАНИЕ КВАРТИРЫ ═══

    waiting_for_new_apartment_number = State()
    """Ожидание нового номера квартиры"""

    waiting_for_new_building_selection = State()
    """Ожидание выбора нового здания"""

    waiting_for_new_entrance_number = State()
    """Ожидание нового номера подъезда"""

    waiting_for_new_floor_number = State()
    """Ожидание нового номера этажа"""

    waiting_for_new_rooms_count = State()
    """Ожидание нового количества комнат"""

    waiting_for_new_area = State()
    """Ожидание новой площади квартиры в кв.м"""

    waiting_for_new_apartment_description = State()
    """Ожидание нового описания квартиры"""

    # ═══ ПОИСК КВАРТИРЫ ═══

    waiting_for_apartment_search = State()
    """Ожидание поискового запроса для квартиры"""

    # ═══ АВТОЗАПОЛНЕНИЕ КВАРТИР ═══

    waiting_for_autofill_building = State()
    """Ожидание выбора здания для автозаполнения"""

    waiting_for_autofill_range = State()
    """Ожидание диапазона номеров квартир для автозаполнения"""


class ApartmentModerationStates(StatesGroup):
    """FSM состояния для модерации заявок на квартиры"""

    # ═══ МОДЕРАЦИЯ ЗАЯВОК ═══

    waiting_for_approval_comment = State()
    """Ожидание комментария при подтверждении заявки"""

    waiting_for_rejection_comment = State()
    """Ожидание комментария при отклонении заявки"""

    viewing_request_details = State()
    """Просмотр деталей заявки (для сохранения контекста)"""


class UserApartmentStates(StatesGroup):
    """FSM состояния для пользовательской работы с квартирами"""

    # ═══ ВЫБОР КВАРТИРЫ ПРИ РЕГИСТРАЦИИ ═══

    waiting_for_yard_choice = State()
    """Ожидание выбора двора пользователем"""

    waiting_for_building_choice = State()
    """Ожидание выбора здания пользователем"""

    waiting_for_apartment_choice = State()
    """Ожидание выбора квартиры пользователем"""

    confirming_apartment_selection = State()
    """Подтверждение выбранной квартиры"""

    # ═══ УПРАВЛЕНИЕ СВОИМИ КВАРТИРАМИ ═══

    viewing_my_apartments = State()
    """Просмотр списка своих квартир"""

    adding_additional_apartment = State()
    """Добавление дополнительной квартиры"""

    waiting_for_apartment_search_user = State()
    """Ожидание поискового запроса от пользователя"""
