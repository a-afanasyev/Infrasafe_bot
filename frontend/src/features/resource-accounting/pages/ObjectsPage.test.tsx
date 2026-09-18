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
import type { ObjectNode, ObjectType, Role, Tag } from '../api/types';
import { ResourceAuthProvider } from '../auth/ResourceAuthContext';
import { ObjectsPage } from './ObjectsPage';

// TEST-068 (порция resource-accounting): страница «Объекты» — дерево с
// сиротами и циклами (COR-10), форма создания/правки, архив, каталоги типов/тегов.
// Настоящий api-клиент модуля через msw (baseUrl абсолютный, конверт { data }).

const BASE = 'http://localhost/res';

function node(overrides: Partial<ObjectNode> & { id: string; name: string }): ObjectNode {
  return { code: null, type_id: 't1', parent_id: null, description: null, sort_order: 0, is_active: true, tags: [], ...overrides };
}

const TYPES: ObjectType[] = [{ id: 't1', name: 'Дом', is_active: true }, { id: 't2', name: 'Старый тип', is_active: false }];
const TAGS: Tag[] = [{ id: 'g1', name: 'ЖК', is_active: true }];

function renderPage(role: Role = 'resource_admin') {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <I18nextProvider i18n={testI18n}>
      <MemoryRouter>
        <ResourceAuthProvider value={{ role, displayName: 'Тест' }}>
          <ObjectsPage />
        </ResourceAuthProvider>
      </MemoryRouter>
      </I18nextProvider>
    </QueryClientProvider>,
  );
}

function mockCatalog(objects: ObjectNode[]) {
  server.use(
    http.get(`${BASE}/v1/objects`, ({ request }) => {
      const status = new URL(request.url).searchParams.get('status');
      return HttpResponse.json({ data: status === 'active' ? objects.filter((o) => o.is_active) : objects });
    }),
    http.get(`${BASE}/v1/object-types`, () => HttpResponse.json({ data: TYPES })),
    http.get(`${BASE}/v1/tags`, () => HttpResponse.json({ data: TAGS })),
  );
}

beforeEach(() => configureResourceApi({ baseUrl: BASE, onUnauthorized: () => {} }));
afterEach(() => vi.restoreAllMocks());

describe('ObjectsPage — дерево', () => {
  it('рендерит корни и детей с отступом, код, тип, теги; сирота и цикл не теряются (COR-10)', async () => {
    mockCatalog([
      node({ id: 'a', name: 'Корпус А', code: 'A-1', tags: TAGS }),
      node({ id: 'a1', name: 'Подъезд 1', parent_id: 'a', type_id: null }),
      node({ id: 'orphan', name: 'Сирота', parent_id: 'archived-parent' }),
      node({ id: 'x', name: 'Цикл X', parent_id: 'y' }),
      node({ id: 'y', name: 'Цикл Y', parent_id: 'x' }),
    ]);
    renderPage();

    expect(await screen.findByText('Корпус А')).toBeInTheDocument();
    expect(screen.getByText('[A-1]')).toBeInTheDocument();
    expect(screen.getByText('ЖК')).toBeInTheDocument();
    expect(screen.getByText('Подъезд 1')).toBeInTheDocument();
    expect(screen.getByText('· —')).toBeInTheDocument(); // тип null → «—»
    expect(screen.getByText('Сирота')).toBeInTheDocument();
    expect(screen.getByText('Цикл X')).toBeInTheDocument();
    expect(screen.getByText('Цикл Y')).toBeInTheDocument();
    const child = screen.getByText('Подъезд 1').closest('.tree-row') as HTMLElement;
    expect(child.style.paddingLeft).toBe('24px');
  });

  it('просмотр: нет кнопок редактирования; пустой список — заглушка', async () => {
    mockCatalog([]);
    renderPage('resource_viewer');
    expect(await screen.findByText('Объекты ещё не созданы')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '+ Новый объект' })).not.toBeInTheDocument();
  });

  it('«Показывать архивные» перезапрашивает без status=active и помечает неактивные', async () => {
    const user = userEvent.setup();
    mockCatalog([node({ id: 'a', name: 'Живой' }), node({ id: 'z', name: 'Архивный', is_active: false })]);
    renderPage();
    expect(await screen.findByText('Живой')).toBeInTheDocument();
    expect(screen.queryByText('Архивный')).not.toBeInTheDocument();

    await user.click(screen.getByLabelText('Показывать архивные'));
    expect(await screen.findByText('Архивный')).toBeInTheDocument();
    // у архивного нет действий, у живого — есть
    const archivedRow = screen.getByText('Архивный').closest('.tree-row') as HTMLElement;
    expect(within(archivedRow).queryByRole('button', { name: 'Изменить' })).not.toBeInTheDocument();
  });

  it('архив: подтверждение через window.confirm, POST /objects/{id}/archive', async () => {
    const user = userEvent.setup();
    mockCatalog([node({ id: 'a', name: 'Корпус А' })]);
    const archived: string[] = [];
    server.use(http.post(`${BASE}/v1/objects/:id/archive`, ({ params }) => {
      archived.push(String(params.id));
      return HttpResponse.json({ data: null });
    }));
    const confirm = vi.spyOn(window, 'confirm').mockReturnValueOnce(false).mockReturnValueOnce(true);
    renderPage();
    const btn = await screen.findByRole('button', { name: 'Архив' });

    await user.click(btn);
    expect(archived).toEqual([]);
    await user.click(btn);
    await waitFor(() => expect(archived).toEqual(['a']));
    expect(confirm).toHaveBeenCalledWith('Архивировать объект «Корпус А»?');
  });
});

describe('ObjectsPage — форма объекта', () => {
  it('«+ Дочерний» подставляет родителя; POST с нормализованным телом; ошибка API остаётся в форме', async () => {
    const user = userEvent.setup();
    mockCatalog([node({ id: 'a', name: 'Корпус А' })]);
    const posts: unknown[] = [];
    server.use(http.post(`${BASE}/v1/objects`, async ({ request }) => {
      posts.push(await request.json());
      return posts.length === 1
        ? HttpResponse.json({ error: { code: 'conflict', message: 'Код уже занят' } }, { status: 409 })
        : HttpResponse.json({ data: node({ id: 'n', name: 'Новый' }) }, { status: 201 });
    }));
    renderPage();

    await user.click(await screen.findByRole('button', { name: '+ Дочерний' }));
    expect(screen.getByText('Новый объект')).toBeInTheDocument();
    const dialog = screen.getByText('Новый объект').closest('.modal, [role="dialog"]') ?? document.body;
    const parent = within(dialog as HTMLElement).getAllByRole('combobox')[1] as HTMLSelectElement;
    expect(parent.value).toBe('a');
    const save = screen.getByRole('button', { name: 'Сохранить' });
    expect(save).toBeDisabled();

    await user.type(screen.getByLabelText('Название *'), '  Подъезд 2 ');
    await user.type(screen.getByLabelText('Код'), 'P2');
    await user.selectOptions(within(dialog as HTMLElement).getAllByRole('combobox')[0], 't1');
    await user.type(screen.getByLabelText('Порядок'), 'x5'); // нецифры отбрасываются
    await user.click(save);

    expect(await screen.findByText('Код уже занят')).toBeInTheDocument();
    expect(posts[0]).toEqual({ name: 'Подъезд 2', code: 'P2', type_id: 't1', parent_id: 'a', description: null, sort_order: 5 });

    await user.click(save);
    await waitFor(() => expect(screen.queryByText('Новый объект')).not.toBeInTheDocument());
    expect(posts).toHaveLength(2);
  });

  it('«Изменить» предзаполняет форму и шлёт PATCH /objects/{id}', async () => {
    const user = userEvent.setup();
    mockCatalog([node({ id: 'a', name: 'Корпус А', code: 'A-1', description: 'Главный', sort_order: 3 })]);
    const patches: { id: string; body: unknown }[] = [];
    server.use(http.patch(`${BASE}/v1/objects/:id`, async ({ params, request }) => {
      patches.push({ id: String(params.id), body: await request.json() });
      return HttpResponse.json({ data: node({ id: 'a', name: 'Корпус Б' }) });
    }));
    renderPage();

    await user.click(await screen.findByRole('button', { name: 'Изменить' }));
    expect(screen.getByText('Редактировать объект')).toBeInTheDocument();
    const name = screen.getByLabelText('Название *') as HTMLInputElement;
    expect(name.value).toBe('Корпус А');
    expect((screen.getByLabelText('Описание') as HTMLTextAreaElement).value).toBe('Главный');
    await user.clear(name);
    await user.type(name, 'Корпус Б');
    await user.click(screen.getByRole('button', { name: 'Сохранить' }));

    await waitFor(() => expect(patches).toHaveLength(1));
    expect(patches[0]).toEqual({ id: 'a', body: { name: 'Корпус Б', code: 'A-1', type_id: 't1', parent_id: null, description: 'Главный', sort_order: 3 } });
  });
});

describe('ObjectsPage — каталоги', () => {
  it('вкладка «Типы объектов»: добавление POST /object-types, «В архив» PATCH is_active=false', async () => {
    const user = userEvent.setup();
    mockCatalog([]);
    const posts: unknown[] = []; const patches: { id: string; body: unknown }[] = [];
    server.use(
      http.post(`${BASE}/v1/object-types`, async ({ request }) => { posts.push(await request.json()); return HttpResponse.json({ data: {} }, { status: 201 }); }),
      http.patch(`${BASE}/v1/object-types/:id`, async ({ params, request }) => { patches.push({ id: String(params.id), body: await request.json() }); return HttpResponse.json({ data: {} }); }),
    );
    renderPage();
    await user.click(screen.getByRole('button', { name: 'Типы объектов' }));

    expect(await screen.findByText('Старый тип')).toBeInTheDocument();
    const add = screen.getByRole('button', { name: 'Добавить' });
    expect(add).toBeDisabled();
    await user.type(screen.getByPlaceholderText('Название…'), ' Гараж ');
    await user.click(add);
    await waitFor(() => expect(posts).toEqual([{ name: 'Гараж' }]));

    const row = screen.getByText('Дом').closest('tr') as HTMLElement;
    await user.click(within(row).getByRole('button', { name: 'В архив' }));
    await waitFor(() => expect(patches).toEqual([{ id: 't1', body: { is_active: false } }]));
    const oldRow = screen.getByText('Старый тип').closest('tr') as HTMLElement;
    expect(within(oldRow).getByRole('button', { name: 'Вернуть' })).toBeInTheDocument();
  });

  it('вкладка «Теги» для viewer: без тулбара и действий', async () => {
    const user = userEvent.setup();
    mockCatalog([]);
    renderPage('resource_viewer');
    await user.click(screen.getByRole('button', { name: 'Теги' }));
    expect(await screen.findByText('ЖК')).toBeInTheDocument();
    expect(screen.queryByPlaceholderText('Название…')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'В архив' })).not.toBeInTheDocument();
  });
});
