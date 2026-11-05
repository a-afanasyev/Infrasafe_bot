import { afterEach, describe, expect, it, vi } from 'vitest';
import { api, ApiError, apiPaged, configureResourceApi } from './client';
// Регистрирует testI18n (ru) как i18n-инстанс react-i18next — запасной текст ошибки берётся из локали.
import '../../../test/test-utils';

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
    expect(err.message).toBe('Ошибка запроса (500)');
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


describe('перевыпуск сессии на 401 (AUD7-SEC-03, сессия — час)', () => {
  const res = (status: number, payload: unknown) =>
    ({ ok: status >= 200 && status < 300, status, json: () => Promise.resolve(payload) }) as Response;

  afterEach(() => {
    configureResourceApi({ onUnauthorized: () => {} });
  });

  it('ждёт перевыпуска и повторяет запрос один раз — показания не теряются', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(res(401, { error: { code: 'unauthorized' } }))
      .mockResolvedValueOnce(res(200, { data: { saved: true } }));
    vi.stubGlobal('fetch', fetchMock);
    const onUnauthorized = vi.fn().mockResolvedValue(undefined);
    configureResourceApi({ onUnauthorized });

    const result = await api('/v1/readings', { method: 'POST', body: { value: 5 } });

    expect(result).toEqual({ saved: true });
    expect(onUnauthorized).toHaveBeenCalledOnce();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('повтор тоже 401 — ошибка, без бесконечного цикла', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(res(401, { error: { code: 'unauthorized' } })));
    configureResourceApi({ onUnauthorized: vi.fn().mockResolvedValue(undefined) });
    await expect(api('/v1/readings')).rejects.toMatchObject({ status: 401 });
    expect(fetch).toHaveBeenCalledTimes(2);
  });

  it('/v1/auth/* не ждёт перевыпуска и не повторяется (его зовёт сам бутстрап)', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(res(401, {})));
    const onUnauthorized = vi.fn(() => new Promise<void>(() => {}));
    configureResourceApi({ onUnauthorized });
    await expect(api('/v1/auth/me')).rejects.toBeInstanceOf(ApiError);
    expect(fetch).toHaveBeenCalledTimes(1);
  });
});
