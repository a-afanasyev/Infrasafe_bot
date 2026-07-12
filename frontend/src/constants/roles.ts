/**
 * Централизованный реестр канонических ролей пользователя (RBAC).
 *
 * Источник истины для бэкенда — utils/constants.USER_ROLES / Settings.USER_ROLES
 * / enum UserRole (см. parity-тест бота test_roles_parity.py). Этот модуль —
 * фронтовый аналог: единый список строк ролей и наборы доступа для route guards
 * (App.tsx ProtectedRoute `allowedRoles`).
 *
 * ТЗ access_control §3.2: добавлены канонические роли модуля контроля доступа
 * `system_admin` и `security_operator`. `executor` и `inspector` НЕ получают
 * доступ к модулю автоматически — они отсутствуют в ACCESS_MODULE_ROLES.
 */

/** Каноническая строка роли (совпадает с users.roles[] на бэкенде). */
export type UserRole =
  | 'applicant'
  | 'executor'
  | 'manager'
  | 'inspector'
  | 'system_admin'
  | 'security_operator'

/** Полный список канонических ролей. */
export const USER_ROLES: readonly UserRole[] = [
  'applicant',
  'executor',
  'manager',
  'inspector',
  'system_admin',
  'security_operator',
] as const

/**
 * Роли, которым разрешён доступ к модулю контроля доступа (web-панель).
 * Намеренно НЕ включает `executor`, `inspector` — у них нет автоматического
 * доступа к access_control (ТЗ §3.2, §6).
 *
 * `applicant` исключён по другой причине: его сценарии (заявки жителя на
 * доступ ТС) живут в Telegram WebApp/TWA, который вынесен в отложенный scope
 * пилота (§6.4, §14.2), а не из-за отсутствия прав по дизайну. Когда TWA-фаза
 * будет в scope — роль появится в соответствующем (TWA-, не web-панельном) guard.
 *
 * Конкретные права внутри модуля (что именно доступно system_admin vs
 * security_operator vs manager) разграничиваются на более поздних фазах;
 * здесь — только регистрация ролей для будущих route guards.
 */
export const ACCESS_MODULE_ROLES: readonly UserRole[] = [
  'manager',
  'system_admin',
  'security_operator',
] as const

/**
 * Роли управления базой/историей модуля доступа (экраны менеджера: «История
 * проездов», «База доступа»). Оператор охраны (`security_operator`) НЕ
 * управляет базой авто/заявок — у него только пост охраны (§6.2/§6.3).
 * Зеркалит RBAC бэкенда: VEHICLES_REQUESTS_ROLES (registry.py).
 */
export const ACCESS_MANAGER_ROLES: readonly UserRole[] = [
  'manager',
  'system_admin',
] as const

/**
 * Роли модуля складского учёта материалов (номенклатура, приход/расход,
 * остатки, журнал, «на закуп»). Исполнитель списывает материалы через
 * Telegram-бот — web-доступ ему не нужен.
 */
export const MATERIALS_MODULE_ROLES: readonly UserRole[] = [
  'manager',
  'system_admin',
] as const

/**
 * Роли нативного раздела «Учёт ресурсов УК» (resource-accounting). Зеркалит
 * роль-гейт backend-минтинга ticket (require_roles manager/system_admin/admin);
 * `admin` не входит в канонический UserRole, поэтому здесь только реальные роли.
 * Ресурс-роль (resource_*) выводится на бэке при выпуске ticket, не тут.
 */
export const RESOURCE_MODULE_ROLES: readonly UserRole[] = [
  'manager',
  'system_admin',
] as const
