import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { I18nextProvider } from 'react-i18next';
import { MemoryRouter } from 'react-router';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { testI18n } from '../../../test/test-utils';
import type { Role, ValidationSummary } from '../api/types';
import { ResourceAuthProvider } from '../auth/ResourceAuthContext';
import { DashboardPage } from './DashboardPage';

const PERIOD = { id: 'p1', month: '2026-07', status: 'open' };

function mockFetch(validation: ValidationSummary) {
  vi.stubGlobal(
    'fetch',
    vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      let payload: unknown = { data: [] };
      if (url.includes('/validate')) payload = { data: validation };
      else if (url.includes('/v1/periods')) payload = { data: [PERIOD] };
      else if (url.includes('/v1/meters')) payload = { data: [], meta: { total: 3, page: 1, per_page: 1 } };
      else if (url.includes('/v1/exports')) payload = { data: [] };
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(payload) } as Response);
    }),
  );
}

function renderPage(role: Role = 'resource_admin') {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <I18nextProvider i18n={testI18n}>
        <MemoryRouter>
          <ResourceAuthProvider value={{ role, displayName: 'Тест' }}>
            <DashboardPage />
          </ResourceAuthProvider>
        </MemoryRouter>
      </I18nextProvider>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('DashboardPage — карточка «Предупреждения / ошибки» (AUD7-CODE-08)', () => {
  it('считает ошибки по длине массива из validate, а не рендерит объекты', async () => {
    mockFetch({
      active_meters: 3,
      entered: 3,
      not_entered: 0,
      by_status: { warning: 2, error: 1 },
      warnings_without_comment: ['m-2'],
      errors: [{ meter_id: 'm-1', message: 'Показание меньше предыдущего' }],
      can_submit: false,
    });
    renderPage();

    const label = await screen.findByText('Предупреждения / ошибки');
    const card = label.parentElement!;
    // Пока validate не пришёл, карточка показывает «—»; ждём именно данных.
    await waitFor(() => expect(card.querySelector('.text-warning')?.textContent).toBe('2'));
    expect(card.querySelector('.text-error')?.textContent).toBe('1');
  });
});
