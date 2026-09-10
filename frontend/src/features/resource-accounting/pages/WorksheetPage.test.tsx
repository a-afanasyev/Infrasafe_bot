import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { I18nextProvider } from 'react-i18next';
import { MemoryRouter } from 'react-router';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { testI18n } from '../../../test/test-utils';
import type { Role } from '../api/types';
import { ResourceAuthProvider } from '../auth/ResourceAuthContext';
import { WorksheetPage } from './WorksheetPage';

const PERIODS = [{ id: 'p1', month: '2026-07', status: 'open' }];

const WORKSHEET = {
  period: PERIODS[0],
  rows: [
    {
      meter_id: 'm1',
      meter_number: 'EL-001',
      meter_name: 'Электро подвал',
      resource_type: 'electricity',
      unit: 'kWh',
      description: 'Общедомовой',
      primary_object_id: 'o1',
      primary_object_name: 'Дом 1',
      consumers: ['Подъезд 1'],
      provider_name: 'Энергосбыт',
      coefficient: '1',
      previous_value: '1000.0000',
      previous_read_at: '2026-06-25',
      reading: null,
    },
  ],
};

const VALIDATION = {
  active_meters: 1,
  entered: 0,
  not_entered: 1,
  by_status: {},
  warnings_without_comment: 0,
  errors: 0,
  can_submit: false,
};

function mockFetchByUrl() {
  vi.stubGlobal(
    'fetch',
    vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      let payload: unknown = { data: null };
      if (url.includes('/v1/periods') && url.includes('/worksheet')) {
        payload = { data: WORKSHEET };
      } else if (url.includes('/v1/periods') && url.includes('/validate')) {
        payload = { data: VALIDATION };
      } else if (url.includes('/v1/periods')) {
        payload = { data: PERIODS };
      } else if (url.includes('/v1/objects')) {
        payload = { data: [] };
      } else if (url.includes('/readings/bulk')) {
        payload = { data: { saved: 1 } };
      }
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve(payload),
      } as Response);
    }),
  );
}

const REVIEW_PERIOD = { id: 'p1', month: '2026-07', status: 'review' };

function mockFetchReview(validation: unknown | 'never') {
  vi.stubGlobal(
    'fetch',
    vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes('/v1/periods') && url.includes('/validate')) {
        if (validation === 'never') return new Promise<Response>(() => {});
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve({ data: validation }),
        } as Response);
      }
      let payload: unknown = { data: [] };
      if (url.includes('/worksheet')) payload = { data: { ...WORKSHEET, period: REVIEW_PERIOD } };
      else if (url.includes('/v1/periods')) payload = { data: [REVIEW_PERIOD] };
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(payload) } as Response);
    }),
  );
}

function renderPage(opts: { role?: string; entryMode?: boolean } = {}) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <I18nextProvider i18n={testI18n}>
        <MemoryRouter>
          <ResourceAuthProvider
            value={{ role: (opts.role ?? 'resource_admin') as Role, displayName: 'Тест' }}
          >
            <WorksheetPage entryMode={opts.entryMode} />
          </ResourceAuthProvider>
        </MemoryRouter>
      </I18nextProvider>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('WorksheetPage', () => {
  it('рендерит строки ведомости из API', async () => {
    mockFetchByUrl();
    renderPage();

    expect(await screen.findByText('EL-001')).toBeInTheDocument();
    expect(screen.getByText('Электро подвал')).toBeInTheDocument();
    expect(screen.getByText('Дом 1')).toBeInTheDocument();
    // предыдущее значение с обрезанными нулями
    expect(screen.getByText('1000')).toBeInTheDocument();
  });

  it('ввод значения активирует кнопку сохранения и отправляет bulk', async () => {
    mockFetchByUrl();
    const user = userEvent.setup();
    renderPage();

    await screen.findByText('EL-001');

    const saveButton = screen.getByRole('button', { name: /Сохранить всё/ });
    expect(saveButton).toBeDisabled();

    const input = screen.getByLabelText('Показание EL-001');
    await user.type(input, '1042.5');

    expect(screen.getByRole('button', { name: /Сохранить всё \(1\)/ })).toBeEnabled();

    await user.click(screen.getByRole('button', { name: /Сохранить всё \(1\)/ }));

    await waitFor(() => {
      const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
      const bulkCall = fetchMock.mock.calls.find(([u]) => String(u).includes('/readings/bulk'));
      expect(bulkCall).toBeTruthy();
      const body = JSON.parse(bulkCall![1].body as string);
      expect(body.items).toEqual([{ meter_id: 'm1', value: '1042.5', comment: null }]);
    });
  });

  it('режим контролёра (entryMode): без управления периодом, без запроса объектов/validate', async () => {
    mockFetchByUrl();
    renderPage({ role: 'resource_meter_entry', entryMode: true });

    await screen.findByText('EL-001');
    // период показан статикой, без выпадашки и кнопки создания
    expect(screen.getByText('Июль 2026')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Создать период/ })).toBeNull();
    expect(screen.queryByText('Статус периода:')).toBeNull();
    // ввод показаний доступен
    expect(screen.getByLabelText('Показание EL-001')).toBeInTheDocument();

    // контролёру недоступные эндпоинты не дёргаются
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    const urls = fetchMock.mock.calls.map(([u]) => String(u));
    expect(urls.some((u) => u.includes('/v1/objects'))).toBe(false);
    expect(urls.some((u) => u.includes('/validate'))).toBe(false);
  });

  it('«Передать» заблокирована, пока validate не получен (AUD7-COR-02)', async () => {
    mockFetchReview('never');
    renderPage();
    const btn = await screen.findByRole('button', { name: 'Передать' });
    expect(btn).toBeDisabled();
  });

  it('«Передать» заблокирована при can_submit=false и доступна при can_submit=true', async () => {
    mockFetchReview({ ...VALIDATION, can_submit: false });
    const first = renderPage();
    expect(await screen.findByRole('button', { name: 'Передать' })).toBeDisabled();
    first.unmount();
    vi.unstubAllGlobals();

    mockFetchReview({ ...VALIDATION, not_entered: 0, entered: 1, can_submit: true });
    renderPage();
    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Передать' })).toBeEnabled();
    });
  });
});
