import type { ListMeta } from './types';

/**
 * API-шов модуля. Хост задаёт baseUrl и обработчик 401 один раз через
 * configureResourceApi(...). credentials:'include' — сессия ресурса живёт в httpOnly-cookie.
 * baseUrl:
 *   - same-origin через edge:  '/uk/api/resource'  (без CORS, cookie first-party) — рекомендуется;
 *   - поддомен (fallback):     'https://resources-api.<домен>' (+ CORS на ресурсе).
 */
interface ResourceApiConfig {
  baseUrl: string;
  onUnauthorized: () => void;
}

const config: ResourceApiConfig = {
  baseUrl: '',
  onUnauthorized: () => {},
};

export function configureResourceApi(partial: Partial<ResourceApiConfig>): void {
  Object.assign(config, partial);
}

export class ApiError extends Error {
  code: string;
  status: number;
  details: unknown;

  constructor(message: string, code: string, status: number, details?: unknown) {
    super(message);
    this.name = 'ApiError';
    this.code = code;
    this.status = status;
    this.details = details;
  }
}

export interface RequestOptions {
  method?: string;
  body?: unknown;
  formData?: FormData;
  params?: Record<string, string | number | boolean | null | undefined>;
}

function buildQuery(params?: RequestOptions['params']): string {
  if (!params) return '';
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') continue;
    search.set(key, String(value));
  }
  const qs = search.toString();
  return qs ? `?${qs}` : '';
}

async function request(path: string, options: RequestOptions): Promise<unknown> {
  const { method = 'GET', body, formData, params } = options;
  const headers: Record<string, string> = {};
  let requestBody: BodyInit | undefined;

  if (formData) {
    requestBody = formData;
  } else if (body !== undefined) {
    headers['Content-Type'] = 'application/json';
    requestBody = JSON.stringify(body);
  }

  const response = await fetch(`${config.baseUrl}${path}${buildQuery(params)}`, {
    method,
    headers,
    body: requestBody,
    credentials: 'include',
  });

  if (response.status === 401) {
    config.onUnauthorized();
  }

  let payload: unknown = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }

  if (!response.ok) {
    const err = (payload as { error?: { code?: string; message?: string; details?: unknown } } | null)
      ?.error;
    throw new ApiError(
      err?.message || `Ошибка запроса (${response.status})`,
      err?.code || 'unknown_error',
      response.status,
      err?.details,
    );
  }

  return payload;
}

/** Выполняет запрос и разворачивает конверт `{ data }`. */
export async function api<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const payload = await request(path, options);
  return (payload as { data: T }).data;
}

/** Для списков с пагинацией: возвращает `{ data, meta }`. */
export async function apiPaged<T>(
  path: string,
  options: RequestOptions = {},
): Promise<{ data: T[]; meta: ListMeta }> {
  const payload = await request(path, options);
  const typed = payload as { data: T[]; meta?: ListMeta };
  return {
    data: typed.data,
    meta: typed.meta ?? { total: typed.data.length, page: 1, per_page: typed.data.length },
  };
}

export function downloadUrl(path: string): string {
  return `${config.baseUrl}${path}`;
}
