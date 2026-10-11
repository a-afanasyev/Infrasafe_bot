/**
 * Канонические строки ролей пользователя (совпадают с users.roles[] на бэкенде).
 *
 * Источник истины для бэкенда — utils/constants.USER_ROLES / Settings.USER_ROLES
 * / enum UserRole (см. parity-тест бота test_roles_parity.py).
 *
 * RBAC A1 (docs/tech/RBAC.md): разделы, пункты меню и кнопки гейтятся НЕ по
 * ролям, а по действиям из профиля (`useCan`, `ProtectedRoute action=...`).
 * Кто что может — решает бэкенд в uk_management_bot/authz/catalog.py. Роль здесь —
 * только признак человека (подпись в карточке сотрудника, бейдж), не право.
 */

/** Каноническая строка роли (совпадает с users.roles[] на бэкенде). */
export type UserRole =
  | 'applicant'
  | 'executor'
  | 'manager'
  | 'inspector'
  | 'system_admin'
  | 'security_operator'
