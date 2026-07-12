/**
 * Публичный API портируемого модуля «Учёт ресурсов УК».
 * Хост монтирует:
 *   <ResourceAccountingProvider config={{ baseUrl, onUnauthorized, basePath, auth?, queryClient? }}>
 *     <ResourceAccountingRoutes />
 *   </ResourceAccountingProvider>
 * См. frontend/INTEGRATION.md.
 */
export { ResourceAccountingProvider } from './ResourceAccountingProvider';
export type { ResourceAccountingConfig } from './ResourceAccountingProvider';
export { ResourceAccountingRoutes } from './ResourceAccountingRoutes';

// Тихий вход (mint→exchange) — опциональный дефолт-хелпер.
export { exchangeTicket, ensureResourceSession } from './session';

// API-конфиг и клиент (если хост хочет дергать resource-API напрямую).
export { configureResourceApi, api, apiPaged, ApiError, downloadUrl } from './api/client';

// Auth-адаптер и чистые роль-хелперы.
export { useResourceAuth } from './auth/ResourceAuthContext';
export type { ResourceAuthValue } from './auth/ResourceAuthContext';
export {
  ROLE_LABELS,
  isAdmin,
  isMeterEntry,
  canEnterReadings,
  canReview,
} from './auth/roles';

export type { Role, AuthUser } from './api/types';
