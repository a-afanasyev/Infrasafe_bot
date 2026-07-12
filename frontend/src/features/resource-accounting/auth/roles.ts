import type { Role } from '../api/types';

/**
 * Чистые роль-хелперы модуля (без зависимости от какого-либо auth-стора).
 * Оперируют РЕСУРС-ролью (resource_*), которую отдаёт resource-сессия (/v1/auth/me),
 * а не ролью хоста. Хост маппит свои роли на ресурс-роль на этапе выпуска ticket.
 */

export const ROLE_LABELS: Record<Role, string> = {
  resource_admin: 'Администратор',
  resource_operator: 'Оператор',
  resource_reviewer: 'Проверяющий',
  resource_viewer: 'Просмотр',
  resource_meter_entry: 'Контролёр',
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
