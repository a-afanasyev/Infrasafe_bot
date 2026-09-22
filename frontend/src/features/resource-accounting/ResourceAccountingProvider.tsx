import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useState, type ReactNode } from 'react';
import { configureResourceApi } from './api/client';
import { ResourceAuthProvider, type ResourceAuthValue } from './auth/ResourceAuthContext';
import { ResourceBasePathContext } from './paths';
import './styles.css';

export interface ResourceAccountingConfig {
  /** База resource-API. Same-origin через edge: '/uk/api/resource'; либо поддомен (+CORS). */
  baseUrl: string;
  /** Вызывается на 401 — хост уводит на свой логин / перезапускает mint→exchange. */
  onUnauthorized: () => void;
  /** Путь монтирования роутов в хосте, напр. '/dashboard/resource-accounting'. По умолчанию ''. */
  basePath?: string;
  /**
   * Auth-значение от хоста { role, displayName, logout? }. Если не задано — модуль сам
   * бутстрапит идентичность из resource-сессии (GET /v1/auth/me).
   */
  auth?: Omit<ResourceAuthValue, 'loading'>;
  /** QueryClient хоста (если УК уже на TanStack Query). Если не задан — модуль создаёт свой. */
  queryClient?: QueryClient;
}

function createModuleQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: 1, refetchOnWindowFocus: false, staleTime: 30_000 },
    },
  });
}

/**
 * Единая обёртка модуля: scoped QueryClient + api-конфиг + auth-адаптер + base-path + scoped CSS.
 * Хост монтирует: <ResourceAccountingProvider config={...}><ResourceAccountingRoutes/></...>.
 */
export function ResourceAccountingProvider({
  config,
  children,
}: {
  config: ResourceAccountingConfig;
  children: ReactNode;
}) {
  // Конфигурируем api синхронно ДО рендера детей (их запросы стартуют на mount).
  // A9-P3-19: не через useMemo (React вправе сбросить мемо — это не гарантия
  // «один раз»). Вызов идемпотентен (Object.assign тех же значений), поэтому
  // прямой вызов в рендере безопасен и не зависит от семантики мемоизации.
  configureResourceApi({ baseUrl: config.baseUrl, onUnauthorized: config.onUnauthorized });

  // A9-P3-19: свой клиент — ровно один на mount (useState-инициализатор), а не
  // useMemo: сброс мемо стёр бы весь кэш модуля. Клиент хоста — в приоритете.
  const [ownQueryClient] = useState(createModuleQueryClient);
  const queryClient = config.queryClient ?? ownQueryClient;

  return (
    <QueryClientProvider client={queryClient}>
      <ResourceBasePathContext.Provider value={config.basePath ?? ''}>
        <ResourceAuthProvider value={config.auth}>
          <div className="ra-root">{children}</div>
        </ResourceAuthProvider>
      </ResourceBasePathContext.Provider>
    </QueryClientProvider>
  );
}
