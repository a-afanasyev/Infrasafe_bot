import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { http, HttpResponse } from 'msw';
import { I18nextProvider } from 'react-i18next';
import { MemoryRouter } from 'react-router';
import { beforeEach, describe, expect, it } from 'vitest';
import { server } from '../../../test/msw/server';
import { testI18n } from '../../../test/test-utils';
import { configureResourceApi } from '../api/client';
import type { AuditEntry, Provider, Role } from '../api/types';
import { ResourceAuthProvider } from '../auth/ResourceAuthContext';
import { AuditPage } from './AuditPage';
import { ProvidersPage } from './ProvidersPage';

// TEST-068 (порция resource-accounting): справочник поставщиков (создание/правка/
// архив) и журнал изменений (фильтры, пагинация, сводка before/after).

const BASE = 'http://localhost/res';

function renderWith(ui: React.ReactElement, role: Role = 'resource_admin') {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <I18nextProvider i18n={testI18n}>
        <MemoryRouter>
          <ResourceAuthProvider value={{ role, displayName: 'Тест' }}>{ui}</ResourceAuthProvider>
        </MemoryRouter>
      </I18nextProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => configureResourceApi({ baseUrl: BASE, onUnauthorized: () => {} }));

describe('ProvidersPage', () => {
  const PROVIDERS: Provider[] = [
    { id: 'p1', name: 'Водоканал', contact: 'vk@example.com', is_active: true },
    { id: 'p2', name: 'Старый', contact: null, is_active: false },
  ];

  it('viewer: таблица без действий и без кнопки создания; пусто — заглушка', async () => {
    server.use(http.get(`${BASE}/v1/providers`, () => HttpResponse.json({ data: PROVIDERS })));
    renderWith(<ProvidersPage />, 'resource_viewer');
    expect(await screen.findByText('Водоканал')).toBeInTheDocument();
    expect(screen.getByText('vk@example.com')).toBeInTheDocument();
    expect(screen.getByText('—')).toBeInTheDocument();
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('создание: POST /providers с trim и contact null; ошибка API остаётся в форме', async () => {
    const user = userEvent.setup();
    server.use(http.get(`${BASE}/v1/providers`, () => HttpResponse.json({ data: [] })));
    const posts: unknown[] = [];
    server.use(http.post(`${BASE}/v1/providers`, async ({ request }) => {
      posts.push(await request.json());
      return posts.length === 1
        ? HttpResponse.json({ error: { message: 'Имя занято' } }, { status: 409 })
        : HttpResponse.json({ data: PROVIDERS[0] }, { status: 201 });
    }));
    renderWith(<ProvidersPage />);
    expect(await screen.findByText('Поставщики не добавлены')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: '+ Новый поставщик' }));
    const save = screen.getByRole('button', { name: 'Сохранить' });
    expect(save).toBeDisabled();
    await user.type(screen.getByLabelText('Название *'), ' Энергосбыт ');
    await user.click(save);
    expect(await screen.findByText('Имя занято')).toBeInTheDocument();
    expect(posts[0]).toEqual({ name: 'Энергосбыт', contact: null });

    await user.click(save);
    await waitFor(() => expect(screen.queryByText('Новый поставщик')).not.toBeInTheDocument());
  });

  it('правка предзаполняет форму и шлёт PATCH; «В архив»/«Вернуть» переключают is_active', async () => {
    const user = userEvent.setup();
    server.use(http.get(`${BASE}/v1/providers`, () => HttpResponse.json({ data: PROVIDERS })));
    const patches: { id: string; body: unknown }[] = [];
    server.use(http.patch(`${BASE}/v1/providers/:id`, async ({ params, request }) => {
      patches.push({ id: String(params.id), body: await request.json() });
      return HttpResponse.json({ data: PROVIDERS[0] });
    }));
    renderWith(<ProvidersPage />);
    const rows = await screen.findAllByRole('row');
    await user.click(within(rows[1]).getByRole('button', { name: 'Изменить' }));
    expect(screen.getByText('Редактировать поставщика')).toBeInTheDocument();
    expect((screen.getByLabelText('Контакты') as HTMLTextAreaElement).value).toBe('vk@example.com');
    await user.clear(screen.getByLabelText('Контакты'));
    await user.click(screen.getByRole('button', { name: 'Сохранить' }));
    await waitFor(() => expect(patches).toEqual([{ id: 'p1', body: { name: 'Водоканал', contact: null } }]));

    await user.click(within(rows[1]).getByRole('button', { name: 'В архив' }));
    await user.click(within(rows[2]).getByRole('button', { name: 'Вернуть' }));
    await waitFor(() => expect(patches).toHaveLength(3));
    expect(patches[1]).toEqual({ id: 'p1', body: { is_active: false } });
    expect(patches[2]).toEqual({ id: 'p2', body: { is_active: true } });
  });
});

describe('AuditPage', () => {
  function entry(overrides: Partial<AuditEntry> & { id: string }): AuditEntry {
    return { entity_type: 'meter', entity_id: 'm-1', action: 'update', before: { name: 'a' }, after: null,
             actor_name: 'Оператор', correlation_id: null, created_at: '2026-09-18T08:00:00Z', ...overrides };
  }

  it('фильтры уходят в запрос (page сбрасывается), пагинация по meta, сводка JSON и «—»', async () => {
    const user = userEvent.setup();
    const calls: Record<string, string>[] = [];
    server.use(http.get(`${BASE}/v1/audit`, ({ request }) => {
      const p = Object.fromEntries(new URL(request.url).searchParams.entries());
      calls.push(p);
      const long = { text: 'x'.repeat(200) };
      return HttpResponse.json({
        data: p.page === '2' ? [] : [entry({ id: 'a1', after: long }), entry({ id: 'a2', actor_name: null, before: null })],
        meta: { total: 45, page: Number(p.page ?? 1), per_page: 20 },
      });
    }));
    renderWith(<AuditPage />);

    expect(await screen.findByText('Стр. 1 из 3 (всего 45)')).toBeInTheDocument();
    expect(calls[0]).toEqual({ page: '1' }); // пустые фильтры не шлются
    const rows = screen.getAllByRole('row');
    expect(within(rows[1]).getByText(/^\{"text":"x{100,}…$/)).toBeInTheDocument();
    expect(within(rows[2]).getAllByText('—')).toHaveLength(3); // actor, before и after
    expect(screen.getByRole('button', { name: '← Назад' })).toBeDisabled();

    await user.click(screen.getByRole('button', { name: 'Вперёд →' }));
    expect(await screen.findByText('Записей не найдено')).toBeInTheDocument();
    expect(calls.at(-1)).toEqual({ page: '2' });

    await user.selectOptions(screen.getByLabelText('Сущность'), 'reading');
    await user.type(screen.getByPlaceholderText('create, update…'), 'c');
    await waitFor(() => expect(calls.at(-1)).toEqual({ entity_type: 'reading', action: 'c', page: '1' }));
  });
});
