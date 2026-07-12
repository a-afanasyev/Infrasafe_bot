import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { api } from '../api/client';
import type { AuthUser, Role } from '../api/types';

/**
 * Auth-шов модуля. Хост либо передаёт готовое значение { role, displayName, logout? },
 * либо не передаёт ничего — тогда модуль сам бутстрапит идентичность из resource-сессии
 * (GET /v1/auth/me). Роль здесь — РЕСУРС-роль (resource_*), она нужна для UI-гейтинга;
 * авторитетную проверку всё равно делает resource-API.
 */
export interface ResourceAuthValue {
  role: Role | undefined;
  displayName: string;
  loading: boolean;
  logout?: () => void | Promise<void>;
}

const ResourceAuthContext = createContext<ResourceAuthValue | null>(null);

// eslint-disable-next-line react-refresh/only-export-components -- ported module: auth hook co-located with its provider
export function useResourceAuth(): ResourceAuthValue {
  const ctx = useContext(ResourceAuthContext);
  if (!ctx) throw new Error('useResourceAuth должен использоваться внутри ResourceAuthProvider');
  return ctx;
}

/**
 * value задан хостом → используем его (host-managed).
 * value не задан → self-bootstrap из /v1/auth/me (module-managed, дефолт).
 */
export function ResourceAuthProvider({
  value,
  children,
}: {
  value?: Omit<ResourceAuthValue, 'loading'>;
  children: ReactNode;
}) {
  const [selfUser, setSelfUser] = useState<AuthUser | null>(null);
  const [selfLoading, setSelfLoading] = useState(!value);

  useEffect(() => {
    if (value) return; // host управляет — не бутстрапим
    let cancelled = false;
    void api<AuthUser>('/v1/auth/me')
      .then((u) => !cancelled && setSelfUser(u))
      .catch(() => !cancelled && setSelfUser(null))
      .finally(() => !cancelled && setSelfLoading(false));
    return () => {
      cancelled = true;
    };
  }, [value]);

  const resolved: ResourceAuthValue = useMemo(() => {
    if (value) return { ...value, loading: false };
    return { role: selfUser?.role, displayName: selfUser?.display_name ?? '', loading: selfLoading };
  }, [value, selfUser, selfLoading]);

  return <ResourceAuthContext.Provider value={resolved}>{children}</ResourceAuthContext.Provider>;
}
