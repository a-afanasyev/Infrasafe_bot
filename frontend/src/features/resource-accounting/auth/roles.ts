import type { Role } from '../api/types';

/**
 * Чистые роль-хелперы модуля (без зависимости от какого-либо auth-стора).
 * Оперируют РЕСУРС-ролью (resource_*), которую отдаёт resource-сессия (/v1/auth/me),
 * а не ролью хоста. Хост маппит свои роли на ресурс-роль на этапе выпуска ticket.
 */

/** i18n-ключи названий ролей (тексты — в локалях хоста, `resourceAccounting.roles.*`). */
export const ROLE_LABEL_KEYS: Record<Role, string> = {
  resource_admin: 'resourceAccounting.roles.resource_admin',
  resource_operator: 'resourceAccounting.roles.resource_operator',
  resource_reviewer: 'resourceAccounting.roles.resource_reviewer',
  resource_viewer: 'resourceAccounting.roles.resource_viewer',
  resource_meter_entry: 'resourceAccounting.roles.resource_meter_entry',
};

export function isMeterEntry(role: Role | undefined): boolean {
  return role === 'resource_meter_entry';
}

export function canEnterReadings(role: Role | undefined): boolean {
  return role === 'resource_admin' || role === 'resource_operator' || role === 'resource_meter_entry';
}

export function canReview(role: Role | undefined): boolean {
  return role === 'resource_admin' || role === 'resource_reviewer';
}

export function isAdmin(role: Role | undefined): boolean {
  return role === 'resource_admin';
}
