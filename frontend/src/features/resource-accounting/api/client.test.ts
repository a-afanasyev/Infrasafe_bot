import { afterEach, describe, expect, it, vi } from 'vitest';
import { api, ApiError, apiPaged } from './client';

function mockFetchOnce(status: number, payload: unknown) {
  const response = {
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(payload),
  } as Response;
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response));
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('api client', () => {
  it('разворачивает конверт { data }', async () => {
    mockFetchOnce(200, { data: { id: '1', name: 'Счётчик' } });
    const result = await api<{ id: string; name: string }>('/v1/meters/1');
    expect(result).toEqual({ id: '1', name: 'Счётчик' });
  });

  it('отправляет credentials: include и JSON-тело', async () => {
    mockFetchOnce(200, { data: { ok: true } });
    await api('/v1/periods', { method: 'POST', body: { month: '2026-07' } });
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toContain('/v1/periods');
    expect(init.credentials).toBe('include');
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body as string)).toEqual({ month: '2026-07' });
  });

  it('ошибка { error } превращается в ApiError с message/code/status', async () => {
    mockFetchOnce(409, {
      error: { code: 'conflict', message: 'Период уже существует', details: { month: '2026-07' } },
    });
    const err = (await api('/v1/periods', { method: 'POST', body: { month: '2026-07' } }).catch(
      (e) => e,
    )) as ApiError;
    expect(err).toBeInstanceOf(ApiError);
    expect(err.message).toBe('Период уже существует');
    expect(err.code).toBe('conflict');
    expect(err.status).toBe(409);
    expect(err.details).toEqual({ month: '2026-07' });
  });

  it('ошибка без тела даёт запасной message', async () => {
    const response = {
      ok: false,
      status: 500,
      json: () => Promise.reject(new Error('not json')),
    } as unknown as Response;
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response));
    const err = (await api('/v1/meters').catch((e) => e)) as ApiError;
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(500);
    expect(err.code).toBe('unknown_error');
  });

  it('apiPaged возвращает data и meta', async () => {
    mockFetchOnce(200, {
      data: [{ id: 'a' }],
      meta: { total: 42, page: 2, per_page: 25 },
    });
    const result = await apiPaged<{ id: string }>('/v1/meters', { params: { page: 2 } });
    expect(result.data).toEqual([{ id: 'a' }]);
    expect(result.meta).toEqual({ total: 42, page: 2, per_page: 25 });
  });
});
