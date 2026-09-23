import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { http, HttpResponse } from 'msw';
import { I18nextProvider } from 'react-i18next';
import { MemoryRouter } from 'react-router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { server } from '../../../test/msw/server';
import { testI18n } from '../../../test/test-utils';
import { configureResourceApi } from '../api/client';
import type { ExportItem, Role } from '../api/types';
import { ResourceAuthProvider } from '../auth/ResourceAuthContext';
import { ExportsPage } from './ExportsPage';

// TEST-068 (порция resource-accounting): акты сверки — создание с фильтрами,
// история, скачивание, отметка «Отправлен», отмена с подтверждением.

const BASE = 'http://localhost/res';

function exp(overrides: Partial<ExportItem> & { id: string }): ExportItem {
  return {
    period_month: '2026-07', provider_id: null, provider_name: null, format: 'xlsx', status: 'generated',
    is_correction: false, filters: null, file_name: null, checksum: null, row_count: 12,
    created_at: '2026-08-01T09:30:00Z', sent_at: null, sent_channel: null, sent_comment: null, ...overrides,
  };
}

function renderPage(role: Role = 'resource_admin') {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <I18nextProvider i18n={testI18n}>
        <MemoryRouter>
          <ResourceAuthProvider value={{ role, displayName: 'Тест' }}>
            <ExportsPage />
          </ResourceAuthProvider>
        </MemoryRouter>
      </I18nextProvider>
    </QueryClientProvider>,
  );
}

function mockLists(exports: ExportItem[]) {
  server.use(
    http.get(`${BASE}/v1/periods`, () => HttpResponse.json({ data: [{ id: 'p6', month: '2026-06', status: 'closed' }, { id: 'p7', month: '2026-07', status: 'open' }] })),
    http.get(`${BASE}/v1/providers`, () => HttpResponse.json({ data: [{ id: 'pr1', name: 'Водоканал', contact: null, is_active: true }] })),
    http.get(`${BASE}/v1/exports`, () => HttpResponse.json({ data: exports })),
  );
}

beforeEach(() => configureResourceApi({ baseUrl: BASE, onUnauthorized: () => {} }));
afterEach(() => vi.restoreAllMocks());

describe('ExportsPage — создание', () => {
  it('периоды новые сверху, кнопка без периода заблокирована, POST /exports с фильтрами; ошибка API под формой', async () => {
    const user = userEvent.setup();
    mockLists([]);
    const posts: unknown[] = [];
    server.use(http.post(`${BASE}/v1/exports`, async ({ request }) => {
      posts.push(await request.json());
      return posts.length === 1
        ? HttpResponse.json({ error: { message: 'Период не закрыт' } }, { status: 409 })
        : HttpResponse.json({ data: exp({ id: 'e1' }) }, { status: 201 });
    }));
    renderPage();

    expect(await screen.findByText('Актов пока нет')).toBeInTheDocument();
    const create = screen.getByRole('button', { name: 'Создать акт' });
    expect(create).toBeDisabled();
    const period = screen.getByLabelText('Период') as HTMLSelectElement;
    const options = await within(period).findAllByRole('option');
    expect(options.map((o) => o.textContent)).toEqual(['— выберите —', 'Июль 2026', 'Июнь 2026']);

    await user.selectOptions(period, '2026-07');
    await user.selectOptions(screen.getByLabelText('Формат'), 'pdf');
    await user.selectOptions(screen.getByLabelText('Поставщик'), 'pr1');
    await user.selectOptions(screen.getByLabelText('Ресурс'), 'cold_water');
    await user.click(screen.getByLabelText('Корректировочный'));
    await user.click(create);

    expect(await screen.findByText('Период не закрыт')).toBeInTheDocument();
    expect(posts[0]).toEqual({ month: '2026-07', format: 'pdf', provider_id: 'pr1', resource_type: 'cold_water', is_correction: true });
    await user.click(create);
    await waitFor(() => expect(screen.queryByText('Период не закрыт')).not.toBeInTheDocument());
  });

  it('просмотр: панели создания нет и нет действий над актами кроме «Скачать»', async () => {
    mockLists([exp({ id: 'e1' })]);
    renderPage('resource_viewer');
    expect(await screen.findByText('Июль 2026')).toBeInTheDocument();
    expect(screen.queryByText('Создать акт')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Скачать' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Отправлен' })).not.toBeInTheDocument();
  });
});

describe('ExportsPage — история и действия', () => {
  it('строки: корр.-чип, поставщик/«Все», статусы, отправлен с каналом; отменённый без кнопок; «Скачать» открывает download', async () => {
    const user = userEvent.setup();
    mockLists([
      exp({ id: 'e1', is_correction: true, provider_name: 'Водоканал', format: 'csv', status: 'sent', sent_at: '2026-08-02T10:00:00Z', sent_channel: 'email' }),
      exp({ id: 'e2', status: 'cancelled', period_month: null, row_count: null }),
    ]);
    const open = vi.spyOn(window, 'open').mockImplementation(() => null);
    renderPage();

    const rows = await screen.findAllByRole('row');
    const r1 = rows[1]; const r2 = rows[2];
    expect(within(r1).getByText('корр.')).toBeInTheDocument();
    expect(within(r1).getByText('CSV')).toBeInTheDocument();
    expect(within(r1).getByText('Водоканал')).toBeInTheDocument();
    expect(within(r1).getByText('Отправлен')).toBeInTheDocument();
    expect(within(r1).getByText(/\(Email\)/)).toBeInTheDocument();
    expect(within(r1).queryByRole('button', { name: 'Отменить' })).not.toBeInTheDocument(); // уже отправлен
    expect(within(r2).getByText('Отменён')).toBeInTheDocument();
    expect(within(r2).getByText('Все')).toBeInTheDocument();
    expect(within(r2).queryByRole('button')).not.toBeInTheDocument();

    await user.click(within(r1).getByRole('button', { name: 'Скачать' }));
    expect(open).toHaveBeenCalledWith(`${BASE}/v1/exports/e1/download`);
  });

  it('«Отправлен»: модалка, POST mark-sent с каналом и комментарием; «Отменить» — только после confirm', async () => {
    const user = userEvent.setup();
    mockLists([exp({ id: 'e1' })]);
    const sent: unknown[] = []; let cancelled = 0;
    server.use(
      http.post(`${BASE}/v1/exports/:id/mark-sent`, async ({ request }) => { sent.push(await request.json()); return HttpResponse.json({ data: null }); }),
      http.post(`${BASE}/v1/exports/:id/cancel`, () => { cancelled += 1; return HttpResponse.json({ error: { message: 'Уже отправлен' } }, { status: 409 }); }),
    );
    vi.spyOn(window, 'confirm').mockReturnValueOnce(false).mockReturnValueOnce(true);
    renderPage();

    await user.click(await screen.findByRole('button', { name: 'Отправлен' }));
    expect(screen.getByText('Отметить как отправленный')).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText('Канал отправки *'), 'edi');
    await user.type(screen.getByLabelText('Комментарий'), ' Реестр №5 ');
    await user.click(screen.getByRole('button', { name: 'Подтвердить' }));
    await waitFor(() => expect(sent).toEqual([{ channel: 'edi', comment: 'Реестр №5' }]));
    await waitFor(() => expect(screen.queryByText('Отметить как отправленный')).not.toBeInTheDocument());

    await user.click(screen.getByRole('button', { name: 'Отменить' }));
    expect(cancelled).toBe(0);
    await user.click(screen.getByRole('button', { name: 'Отменить' }));
    await waitFor(() => expect(cancelled).toBe(1));
    expect(await screen.findByRole('alert')).toHaveTextContent('Уже отправлен');
    await user.click(within(screen.getByRole('alert')).getByRole('button', { name: '×' }));
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });
});
