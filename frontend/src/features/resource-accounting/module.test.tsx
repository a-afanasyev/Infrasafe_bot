import { render, screen } from '@testing-library/react';
import { QueryClient, useQueryClient } from '@tanstack/react-query';
import { downloadUrl } from './api/client';
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

// A9-P3-19: QueryClient модуля создавался в useMemo — React вправе сбросить
// мемо, и кэш модуля пропал бы. Теперь useState(() => …): один клиент на mount,
// даже при новом объекте config на каждом рендере хоста.
describe('ResourceAccountingProvider — стабильный QueryClient', () => {
  function Probe({ seen }: { seen: QueryClient[] }) {
    seen.push(useQueryClient());
    return null;
  }

  function tree(seen: QueryClient[], baseUrl: string) {
    return (
      <ResourceAccountingProvider config={{ baseUrl, onUnauthorized: () => {}, auth: { role: 'resource_admin', displayName: 'X' } }}>
        <Probe seen={seen} />
      </ResourceAccountingProvider>
    );
  }

  it('один клиент на весь жизненный цикл, api переконфигурируется на смену baseUrl', () => {
    const seen: QueryClient[] = [];
    const { rerender } = render(tree(seen, '/a'));
    rerender(tree(seen, '/b'));
    expect(new Set(seen).size).toBe(1);
    expect(downloadUrl('/v1/x')).toBe('/b/v1/x');
  });

  it('клиент хоста имеет приоритет', () => {
    const host = new QueryClient();
    const seen: QueryClient[] = [];
    render(
      <ResourceAccountingProvider config={{ baseUrl: '', onUnauthorized: () => {}, queryClient: host, auth: { role: 'resource_admin', displayName: 'X' } }}>
        <Probe seen={seen} />
      </ResourceAccountingProvider>,
    );
    expect(seen[0]).toBe(host);
  });
});
