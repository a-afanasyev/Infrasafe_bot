import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useMemo, type ReactNode } from 'react';
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
  useMemo(
    () => configureResourceApi({ baseUrl: config.baseUrl, onUnauthorized: config.onUnauthorized }),
    [config.baseUrl, config.onUnauthorized],
  );

  const queryClient = useMemo(
    () =>
      config.queryClient ??
      new QueryClient({
        defaultOptions: {
          queries: { retry: 1, refetchOnWindowFocus: false, staleTime: 30_000 },
        },
      }),
    [config.queryClient],
  );

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
