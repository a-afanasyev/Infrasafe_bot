"""Parity-тест ролевой модели (ТЗ access_control §3.2).

Запрещает расхождение трёх источников канонических строк ролей:
  * Settings.USER_ROLES         (config/settings.py)
  * constants.USER_ROLES        (utils/constants.py)
  * enum UserRole               (utils/enums.py, через контрактный .db_value)

Любое добавление/удаление роли обязано синхронно затронуть все три источника,
иначе тест падает. Дополнительно проверяет, что канонические роли пилота
доступа (system_admin, security_operator) присутствуют и проходят validate_role.
"""
from uk_management_bot.config.settings import settings
from uk_management_bot.utils import constants
from uk_management_bot.utils.enums import UserRole
from uk_management_bot.utils.validators import Validator

# Канонические роли модуля контроля доступа (ТЗ §3.2).
ACCESS_CONTROL_ROLES = ("system_admin", "security_operator")


def test_role_sources_in_parity():
    """Три источника ролей должны описывать один и тот же набор строк."""
    settings_roles = set(settings.USER_ROLES)
    constants_roles = set(constants.USER_ROLES)
    enum_roles = {r.db_value for r in UserRole}

    assert settings_roles == constants_roles, (
        "Рассинхрон Settings.USER_ROLES vs constants.USER_ROLES: "
        f"{settings_roles ^ constants_roles}"
    )
    assert constants_roles == enum_roles, (
        "Рассинхрон constants.USER_ROLES vs enum UserRole: "
        f"{constants_roles ^ enum_roles}"
    )


def test_access_control_roles_present_in_all_sources():
    """Новые роли §3.2 должны быть синхронно во всех трёх источниках."""
    settings_roles = set(settings.USER_ROLES)
    constants_roles = set(constants.USER_ROLES)
    enum_roles = {r.db_value for r in UserRole}

    for role in ACCESS_CONTROL_ROLES:
        assert role in settings_roles, f"{role} отсутствует в Settings.USER_ROLES"
        assert role in constants_roles, f"{role} отсутствует в constants.USER_ROLES"
        assert role in enum_roles, f"{role} отсутствует в enum UserRole"


def test_validate_role_accepts_access_control_roles():
    """validate_role (читает constants.USER_ROLES) принимает новые роли."""
    for role in ACCESS_CONTROL_ROLES:
        is_valid, _ = Validator.validate_role(role)
        assert is_valid is True, f"validate_role отклонил каноническую роль {role}"
