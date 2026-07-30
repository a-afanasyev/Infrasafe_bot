import { render, screen } from '@testing-library/react';
import { I18nextProvider } from 'react-i18next';
import { MemoryRouter } from 'react-router';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { testI18n } from '../../test/test-utils';
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
      <I18nextProvider i18n={testI18n}>
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
        </MemoryRouter>
      </I18nextProvider>,
    );
    // host-auth задан → без self-bootstrap /v1/auth/me; страница «Счётчики» рендерится
    expect(await screen.findByRole('heading', { name: 'Счётчики' })).toBeInTheDocument();
  });

  it('роль контролёра → единственный роут ввода показаний', async () => {
    mockFetch();
    render(
      <I18nextProvider i18n={testI18n}>
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
        </MemoryRouter>
      </I18nextProvider>,
    );
    expect(await screen.findByRole('heading', { name: 'Ввод показаний' })).toBeInTheDocument();
  });
});
