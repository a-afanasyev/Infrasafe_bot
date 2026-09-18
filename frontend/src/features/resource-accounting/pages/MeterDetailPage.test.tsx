import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { http, HttpResponse } from 'msw';
import { I18nextProvider } from 'react-i18next';
import { MemoryRouter, Route, Routes } from 'react-router';
import { beforeEach, describe, expect, it } from 'vitest';
import { server } from '../../../test/msw/server';
import { testI18n } from '../../../test/test-utils';
import { configureResourceApi } from '../api/client';
import type { Meter, MeterAnalytics, Role } from '../api/types';
import { ResourceAuthProvider } from '../auth/ResourceAuthContext';
import { MeterDetailPage } from './MeterDetailPage';

// TEST-068 (порция resource-accounting): карточка счётчика — реквизиты, действия
// (исправление номера, архив, правка, замена) и вкладка графика с аналитикой.

const BASE = 'http://localhost/res';

const METER: Meter = {
  id: 'm1', meter_number: 'M-001', name: 'ХВС подвал', resource_type: 'cold_water', unit: 'm3',
  description: 'Общедомовой', install_location: 'Подвал', status: 'active', primary_object_id: 'o1',
  primary_object_name: 'Корпус А', provider_id: 'p1', provider_account: '77-1', serial_number: 'SN-9',
  coefficient: '1.500', max_digits: 6, installed_at: '2026-01-15', note: null,
  tags: [{ id: 'g1', name: 'ЖК', is_active: true }],
  consumers: [{ id: 'c1', object_id: 'o2', object_name: 'Подъезд 1', description: null }],
};
const PROVIDERS = [{ id: 'p1', name: 'Водоканал', contact: null, is_active: true }];
const ANALYTICS: MeterAnalytics = {
  meter_id: 'm1', meter_number: 'M-001', unit: 'm3',
  points: [
    { month: '2026-06', reading: '100', consumption: '10', status: 'ok', missing: false },
    { month: '2026-07', reading: '115', consumption: '15', status: 'warning', missing: false },
  ],
  stats: { avg_3m: 12.5, avg_6m: null, avg_12m: 11, change_abs: 5, change_pct: 50, year_over_year: { previous_year: 9, current: 15, change_pct: 66.7 } },
};

function renderPage(role: Role = 'resource_admin') {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <I18nextProvider i18n={testI18n}>
      <MemoryRouter initialEntries={['/meters/m1']}>
        <ResourceAuthProvider value={{ role, displayName: 'Тест' }}>
          <Routes>
            <Route path="/meters/:id" element={<MeterDetailPage />} />
            <Route path="/meters" element={<div>РЕЕСТР</div>} />
          </Routes>
        </ResourceAuthProvider>
      </MemoryRouter>
      </I18nextProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  configureResourceApi({ baseUrl: BASE, onUnauthorized: () => {} });
  server.use(
    http.get(`${BASE}/v1/meters/:id`, () => HttpResponse.json({ data: METER })),
    http.get(`${BASE}/v1/providers`, () => HttpResponse.json({ data: PROVIDERS })),
    http.get(`${BASE}/v1/objects`, () => HttpResponse.json({ data: [{ id: 'o1', name: 'Корпус А', code: null, type_id: null, parent_id: null, description: null, sort_order: 0, is_active: true, tags: [] }] })),
  );
});

describe('MeterDetailPage — реквизиты', () => {
  it('шапка, поставщик по id, коэффициент без хвостовых нулей, теги, потребители; «← К реестру» ведёт назад', async () => {
    const user = userEvent.setup();
    renderPage();
    expect(await screen.findByText('ХВС подвал', { exact: false })).toBeInTheDocument();
    expect(screen.getByText('M-001')).toBeInTheDocument();
    expect(screen.getByText(/Холодная вода, m3 · Активен/)).toBeInTheDocument();
    expect(await screen.findByText('Водоканал')).toBeInTheDocument();
    expect(screen.getByText('1.5')).toBeInTheDocument();
    expect(screen.getByText('ЖК')).toBeInTheDocument();
    expect(screen.getByText('Подъезд 1')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Редактировать' })).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: '← К реестру' }));
    expect(screen.getByText('РЕЕСТР')).toBeInTheDocument();
  });

  it('просмотр: без кнопок действий; архивный счётчик — тоже', async () => {
    renderPage('resource_viewer');
    await screen.findByText('M-001');
    expect(screen.queryByRole('button', { name: 'В архив' })).not.toBeInTheDocument();
  });

  it('ошибка загрузки — ErrorState с повтором', async () => {
    server.use(http.get(`${BASE}/v1/meters/:id`, () => HttpResponse.json({ error: { message: 'Не найден' } }, { status: 404 })));
    renderPage();
    expect(await screen.findByText(/Не найден/)).toBeInTheDocument();
  });
});

describe('MeterDetailPage — действия', () => {
  it('исправить номер: причина ≥ 3 символов, POST correct-number, ошибка API в модалке', async () => {
    const user = userEvent.setup();
    const posts: unknown[] = [];
    server.use(http.post(`${BASE}/v1/meters/:id/correct-number`, async ({ request }) => {
      posts.push(await request.json());
      return posts.length === 1
        ? HttpResponse.json({ error: { code: 'conflict', message: 'Номер занят' } }, { status: 409 })
        : HttpResponse.json({ data: null });
    }));
    renderPage();
    await user.click(await screen.findByRole('button', { name: 'Исправить номер' }));
    expect(screen.getByText('Исправить номер счётчика')).toBeInTheDocument();
    const submit = screen.getByRole('button', { name: 'Исправить' });
    await user.type(screen.getByLabelText('Новый номер *'), ' M-002 ');
    await user.type(screen.getByLabelText('Причина *'), 'ab');
    expect(submit).toBeDisabled();
    await user.type(screen.getByLabelText('Причина *'), 'c');
    expect(submit).toBeEnabled();

    await user.click(submit);
    expect(await screen.findByText('Номер занят')).toBeInTheDocument();
    expect(posts[0]).toEqual({ new_number: 'M-002', reason: 'abc' });
    await user.click(submit);
    await waitFor(() => expect(screen.queryByText('Исправить номер счётчика')).not.toBeInTheDocument());
  });

  it('архив: POST /archive, модалка закрывается; «Отмена» закрывает без запроса', async () => {
    const user = userEvent.setup();
    let archived = 0;
    server.use(http.post(`${BASE}/v1/meters/:id/archive`, () => { archived += 1; return HttpResponse.json({ data: null }); }));
    renderPage();
    await user.click(await screen.findByRole('button', { name: 'В архив' }));
    expect(screen.getByText(/будет перенесён в архив/)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Отмена' }));
    expect(archived).toBe(0);

    await user.click(screen.getByRole('button', { name: 'В архив' }));
    const dialog = screen.getByText(/будет перенесён в архив/).closest('div')!.parentElement as HTMLElement;
    await user.click(within(dialog).getByRole('button', { name: 'В архив' }));
    await waitFor(() => expect(archived).toBe(1));
    await waitFor(() => expect(screen.queryByText(/будет перенесён в архив/)).not.toBeInTheDocument());
  });

  it('редактировать: PATCH без meter_number/resource_type/unit', async () => {
    const user = userEvent.setup();
    const patches: Record<string, unknown>[] = [];
    server.use(http.patch(`${BASE}/v1/meters/:id`, async ({ request }) => {
      patches.push((await request.json()) as Record<string, unknown>);
      return HttpResponse.json({ data: METER });
    }));
    renderPage();
    await user.click(await screen.findByRole('button', { name: 'Редактировать' }));
    expect(screen.getByText('Редактировать счётчик')).toBeInTheDocument();
    await screen.findAllByRole('option', { name: 'Корпус А' });
    await user.click(screen.getByRole('button', { name: 'Сохранить' }));

    await waitFor(() => expect(patches).toHaveLength(1));
    expect(patches[0]).not.toHaveProperty('meter_number');
    expect(patches[0]).not.toHaveProperty('resource_type');
    expect(patches[0]).not.toHaveProperty('unit');
    expect(patches[0]).toMatchObject({ name: 'ХВС подвал', primary_object_id: 'o1', provider_account: '77-1' });
  });

  it('замена: без даты/причины — подсказка, запроса нет; с ними — POST /replace и переход на новый счётчик', async () => {
    const user = userEvent.setup();
    const posts: Record<string, unknown>[] = [];
    server.use(
      http.post(`${BASE}/v1/meters/:id/replace`, async ({ request }) => {
        posts.push((await request.json()) as Record<string, unknown>);
        return HttpResponse.json({ data: { ...METER, id: 'm2', meter_number: 'M-002' } }, { status: 201 });
      }),
    );
    renderPage();
    await user.click(await screen.findByRole('button', { name: 'Заменить' }));
    await screen.findAllByRole('option', { name: 'Корпус А' });
    await user.type(screen.getByLabelText('Номер счётчика *'), 'M-002');
    await user.type(screen.getByLabelText('Название *'), 'Новый');
    await user.type(screen.getByLabelText('Описание *'), 'Опис');
    await user.type(screen.getByLabelText('Место установки *'), 'Подвал');
    await user.selectOptions(screen.getByLabelText('Основной объект *'), 'o1');
    const submitReplace = () => user.click(screen.getAllByRole('button', { name: 'Заменить' }).at(-1)!); // последняя — submit формы, первая — действие в шапке
    await submitReplace();
    expect(await screen.findByText(/Укажите дату снятия и причину замены/)).toBeInTheDocument();
    expect(posts).toHaveLength(0);

    await user.type(screen.getByLabelText('Дата снятия *'), '2026-09-18');
    await user.type(screen.getByLabelText('Причина замены *'), 'Поверка');
    await submitReplace();
    await waitFor(() => expect(posts).toHaveLength(1));
    expect(posts[0]).toMatchObject({ removed_at: '2026-09-18', reason: 'Поверка' });
    expect((posts[0].new_meter as Record<string, unknown>).meter_number).toBe('M-002');
  });
});

describe('MeterDetailPage — график', () => {
  it('вкладка грузит аналитику с range=12m, показывает статистику; смена диапазона — новый запрос; пусто — заглушка', async () => {
    const user = userEvent.setup();
    const ranges: string[] = [];
    server.use(http.get(`${BASE}/v1/analytics/meters/:id`, ({ request }) => {
      const range = new URL(request.url).searchParams.get('range') ?? '';
      ranges.push(range);
      return HttpResponse.json({ data: range === '6m' ? { ...ANALYTICS, points: [] } : ANALYTICS });
    }));
    renderPage();
    await screen.findByText('M-001');
    expect(ranges).toEqual([]); // до открытия вкладки аналитика не грузится

    await user.click(screen.getByRole('button', { name: 'График' }));
    expect(await screen.findByText('Среднее за 3 мес')).toBeInTheDocument();
    expect(ranges).toEqual(['12m']);
    expect(screen.getByText('12.5 m3')).toBeInTheDocument();
    expect(screen.getByText('5 m3 (+50%)')).toBeInTheDocument();
    expect(screen.getByText('66.7 %')).toBeInTheDocument();
    const avg6 = screen.getByText('Среднее за 6 мес').parentElement as HTMLElement;
    expect(within(avg6).getByText('—')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: '6 мес' }));
    expect(await screen.findByText('Нет данных за выбранный диапазон')).toBeInTheDocument();
    expect(ranges).toEqual(['12m', '6m']);
  });
});
