import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ResourceAccountingProvider } from './ResourceAccountingProvider';
import { ResourceAccountingRoutes } from './ResourceAccountingRoutes';

/**
 * Мини-хост: проверяем, что модуль монтируется с host-provided auth-адаптером и моковым fetch,
 * и роуты рендерятся под своим basePath. Это smoke-тест портируемости (без standalone-инфраструктуры).
 */
function mockFetch() {
  vi.stubGlobal(
    'fetch',
    vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      let payload: unknown = { data: null };
      if (url.includes('/v1/meters')) payload = { data: [], meta: { total: 0, page: 1, per_page: 25 } };
      else if (url.includes('/v1/providers')) payload = { data: [] };
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(payload) } as Response);
    }),
  );
}

afterEach(() => vi.unstubAllGlobals());

describe('ResourceAccounting module mount', () => {
  it('монтируется с host-auth и рендерит роут /meters', async () => {
    mockFetch();
    render(
      <MemoryRouter initialEntries={['/meters']}>
        <ResourceAccountingProvider
          config={{
            baseUrl: '',
            onUnauthorized: () => {},
            basePath: '',
            auth: { role: 'resource_admin', displayName: 'Хост-пользователь' },
          }}
        >
          <ResourceAccountingRoutes />
        </ResourceAccountingProvider>
      </MemoryRouter>,
    );
    // host-auth задан → без self-bootstrap /v1/auth/me; страница «Счётчики» рендерится
    expect(await screen.findByRole('heading', { name: 'Счётчики' })).toBeInTheDocument();
  });

  it('роль контролёра → единственный роут ввода показаний', async () => {
    mockFetch();
    render(
      <MemoryRouter initialEntries={['/anything']}>
        <ResourceAccountingProvider
          config={{
            baseUrl: '',
            onUnauthorized: () => {},
            auth: { role: 'resource_meter_entry', displayName: 'Контролёр' },
          }}
        >
          <ResourceAccountingRoutes />
        </ResourceAccountingProvider>
      </MemoryRouter>,
    );
    expect(await screen.findByRole('heading', { name: 'Ввод показаний' })).toBeInTheDocument();
  });
});
