"""
Сервис для работы со справочником адресов.

ARCH-014: write-методы — тонкие async-обёртки над services/addresses/core.
Они открывают собственную AsyncSession (sync-аргумент `session` игнорируется,
сохранён только для обратной совместимости сигнатур) и переводят доменные
исключения core в текущий контракт Tuple[Entity|None, error_str|None].
Read-методы по-прежнему работают на переданной sync-сессии.
"""
# AUD5-ARCH-3 волна 6: block-move файла services/address_service.py
# (1087 строк) в пакет. Публичный API и dotted-path импортёров сохранены;
# класс AddressService собирается наследованием mixin'ов, тела методов
# перенесены байт-в-байт. Реэкспорты ниже (_core, _async_session, _Unset,
# _UNSET, AddressError) сохраняют прежний module-namespace для тестов.

from uk_management_bot.services.addresses import core as _core  # noqa: F401
from uk_management_bot.services.addresses.exceptions import AddressError  # noqa: F401

from ._helpers import _UNSET, _Unset, _async_session  # noqa: F401
from . import stats as _stats_module
from .yards import YardsMixin
from .buildings import BuildingsMixin
from .apartments import ApartmentsMixin
from .residency import ResidencyMixin
from .stats import StatsMixin
from .user_scope import UserScopeMixin


class AddressService(
    YardsMixin,
    BuildingsMixin,
    ApartmentsMixin,
    ResidencyMixin,
    StatsMixin,
    UserScopeMixin,
):
    """Сервис для управления справочником адресов и модерацией"""


# stats.get_user_approved_apartments вызывает AddressService.…_sync по имени
# модульного global'а (тело сохранено байт-в-байт) — инжектим собранный класс.
_stats_module.AddressService = AddressService

__all__ = [
    "AddressService",
    "AddressError",
    "_core",
    "_async_session",
    "_Unset",
    "_UNSET",
]
