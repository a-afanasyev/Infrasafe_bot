import { describe, it, expect, beforeEach, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { Route, Routes } from 'react-router'
import { render, screen, waitFor } from '../../test/test-utils'
import { server } from '../../test/msw/server'
import { useAuthStore } from '../../stores/authStore'
import { actionsFor } from '../../test/authz'
import { ProtectedRoute } from '../../App'
import { uploadPassportPhoto, type PassportSchema, type PassportView } from '../../features/passport/api'
import PassportListPage from './PassportListPage'
import PassportHousePage from './PassportHousePage'

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }))

const field = (key: string, type: 'int' | 'choice' | 'text', ru: string, extra: object = {}) => ({
  kind: 'field' as const, key, type, ru, uz: ru, unit: null, form_no: null, computed: false, share: null, show_if: null, ...extra,
})

const SCHEMA: PassportSchema = {
  version: 1,
  sections: [{
    key: 's1', no: 1, ru: 'Общие сведения', uz: 'Umumiy',
    items: [
      field('floors', 'int', 'Количество этажей', { form_no: '2.10' }),
      field('attic', 'choice', 'Чердак', { options: [
        { key: 'yes', ru: 'есть', uz: 'bor', other: false }, { key: 'no', ru: 'нет', uz: "yo'q", other: false }] }),
      field('attic_area', 'int', 'Площадь чердака', { show_if: ['attic', ['yes']] }),
      { kind: 'group', key: 'windows', ru: 'Окна', uz: 'Derazalar', share: null, show_if: null,
        fields: [field('count', 'int', 'Количество')] },
    ],
  }],
}

const VIEW: PassportView = {
  building_id: 5, address: 'ул. Тестовая, 5', status: 'collecting', version: 3, revision_no: 0,
  progress: { done: 1, total: 4 }, editable: true,
  values: { floors: 9 }, unknown: {}, absent: [], shared_from: {},
  meta: { inspection_date: null, responsible_name: null, note: null },
  issues: [], missing: ['attic', 'windows'], hints: {}, photos: [], updated_at: null, updated_by_name: null,
}

function mock(view: PassportView = VIEW) {
  const patches: Record<string, unknown>[] = []
  let current = view
  server.use(
    http.get('*/api/v2/passports/schema', () => HttpResponse.json(SCHEMA)),
    http.get('*/api/v2/passports', () => HttpResponse.json([view])),
    http.get('*/api/v2/passports/buildings/5', () => HttpResponse.json(current)),
    http.patch('*/api/v2/passports/buildings/5', async ({ request }) => {
      const body = (await request.json()) as { values?: Record<string, number> }
      patches.push(body)
      current = { ...current, version: current.version + 1, values: { ...current.values, ...body.values } }
      return HttpResponse.json(current)
    }),
  )
  return { patches, setCurrent: (next: PassportView) => { current = next } }
}

const as = (role: string) =>
  useAuthStore.setState({ user: { id: 1, roles: [role], actions: actionsFor([role]) }, isAuthenticated: true, hydrating: false })

const renderHouse = () => render(
  <Routes><Route path="/dashboard/passports/:id" element={<PassportHousePage />} /></Routes>,
  { routerEntries: ['/dashboard/passports/5'] },
)

beforeEach(() => as('engineer'))

describe('Паспорта домов', () => {
  it('список: дом плиткой со статусом и прогрессом', async () => {
    mock()
    render(<PassportListPage />)
    expect(await screen.findByText('ул. Тестовая, 5')).toBeInTheDocument()
    expect(screen.getByText('Сбор данных')).toBeInTheDocument()
    expect(screen.getByText('1 / 4 · 25 %')).toBeInTheDocument()
  })

  it('форма рисуется по схеме, зависимый пункт появляется по условию', async () => {
    mock({ ...VIEW, values: { floors: 9, attic: 'yes' } })
    renderHouse()
    expect(await screen.findByLabelText('Количество этажей')).toHaveValue('9')
    expect(screen.getByLabelText('Площадь чердака')).toBeInTheDocument()
  })

  it('автосохранение шлёт версию; скрытый пункт не показан', async () => {
    const { patches } = mock()
    const user = userEvent.setup()
    renderHouse()
    const floors = await screen.findByLabelText('Количество этажей')
    expect(screen.queryByLabelText('Площадь чердака')).not.toBeInTheDocument()
    await user.clear(floors)
    await user.type(floors, '12')
    await user.tab()
    await waitFor(() => expect(patches).toEqual([{ values: { floors: 12 }, expected_version: 3 }]))
    expect(await screen.findByLabelText('Количество этажей')).toHaveValue('12')
  })

  it('409 stale: форма показывает актуальное значение, а не затирает его', async () => {
    const { setCurrent } = mock()
    server.use(http.patch('*/api/v2/passports/buildings/5', () =>
      HttpResponse.json({ detail: { code: 'stale', keys: ['floors'] } }, { status: 409 })))
    const user = userEvent.setup()
    renderHouse()
    const floors = await screen.findByLabelText('Количество этажей')
    setCurrent({ ...VIEW, version: 4, values: { floors: 16 } })
    await user.clear(floors)
    await user.type(floors, '12')
    await user.tab()
    await waitFor(() => expect(screen.getByLabelText('Количество этажей')).toHaveValue('16'))
  })

  it('«нет данных» уходит с причиной', async () => {
    const { patches } = mock({ ...VIEW, values: {} })
    const user = userEvent.setup()
    renderHouse()
    await screen.findByLabelText('Количество этажей')
    await user.click(screen.getAllByRole('button', { name: 'нет данных' })[0])
    await user.type(screen.getByLabelText('Почему нет данных'), 'нет документов')
    await user.click(screen.getByRole('button', { name: 'Сохранить' }))
    await waitFor(() => expect(patches).toEqual([{ unknown: { floors: 'нет документов' }, expected_version: 3 }]))
  })

  it('группу строк можно закрыть как «нет данных»', async () => {
    const { patches } = mock()
    const user = userEvent.setup()
    renderHouse()
    await screen.findByLabelText('Количество этажей')
    await user.click(screen.getAllByRole('button', { name: 'нет данных' }).at(-1)!)
    await user.type(screen.getByLabelText('Почему нет данных'), 'замеров нет')
    await user.click(screen.getByRole('button', { name: 'Сохранить' }))
    await waitFor(() => expect(patches).toEqual([{ unknown: { windows: 'замеров нет' }, expected_version: 3 }]))
  })

  it('строки группы сохраняются кнопкой, числом', async () => {
    const { patches } = mock()
    const user = userEvent.setup()
    renderHouse()
    await screen.findByLabelText('Количество этажей')
    await user.click(screen.getByRole('button', { name: 'Добавить строку' }))
    await user.type(screen.getByLabelText('Количество'), '4')
    await user.click(screen.getByRole('button', { name: 'Сохранить строки' }))
    await waitFor(() => expect(patches).toEqual([{ values: { windows: [{ count: 4 }] }, expected_version: 3 }]))
  })

  it('инженер не подписывает; менеджер подписывает заполненный', async () => {
    mock({ ...VIEW, status: 'filled' })
    const first = renderHouse()
    await screen.findByLabelText('Количество этажей')
    expect(screen.queryByRole('button', { name: 'Подписать' })).not.toBeInTheDocument()
    first.unmount()
    as('manager')
    renderHouse()
    expect(await screen.findByRole('button', { name: 'Подписать' })).toBeInTheDocument()
  })

  it('инспектор читает: полей правки, статуса и подписи нет', async () => {
    as('inspector')
    mock({ ...VIEW, status: 'filled' })
    renderHouse()
    expect(await screen.findByLabelText('Количество этажей')).toBeDisabled()
    expect(screen.queryByLabelText('Статус')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Подписать' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'нет данных' })).not.toBeInTheDocument()
  })

  it('загрузка фото повторяется с тем же ключом операции', async () => {
    const keys: string[] = []
    server.use(http.post('*/api/v2/passports/buildings/5/photos', async ({ request }) => {
      // Ключ берём из сырого тела: разбор multipart в undici зависит от версии Node
      // и на файле из jsdom падает.
      keys.push(/name="op_key"\r\n\r\n([^\r]+)/.exec(await request.text())?.[1] ?? '')
      return keys.length === 1
        ? HttpResponse.json({ detail: { code: 'media_unavailable', keys: [] } }, { status: 503 })
        : HttpResponse.json({ id: 1 })
    }))
    await uploadPassportPhoto(5, 's1', new File(['x'], 'a.png', { type: 'image/png' }), 0)
    expect(keys).toHaveLength(2)
    expect(keys[0]).toMatch(/^[0-9a-f-]{36}$/)
    expect(keys[0]).toBe(keys[1])
  })

  it('фото раздела: превью, удаление — только у редактора', async () => {
    const photo = { id: 9, section: 's1', uploaded_by_name: 'Инженер', uploaded_at: null }
    const deleted: string[] = []
    mock({ ...VIEW, photos: [photo] })
    server.use(
      http.get('*/api/v2/passports/buildings/5/photos/9/file', () => new HttpResponse(new Blob(['x'], { type: 'image/jpeg' }))),
      http.delete('*/api/v2/passports/buildings/5/photos/:id', ({ params }) => { deleted.push(String(params.id)); return new HttpResponse(null, { status: 204 }) }),
    )
    const user = userEvent.setup()
    const first = renderHouse()
    expect(await screen.findByAltText('Инженер')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Убрать фото' }))
    await waitFor(() => expect(deleted).toEqual(['9']))
    first.unmount()
    as('inspector')
    renderHouse()
    expect(await screen.findByAltText('Инженер')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Убрать фото' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Добавить фото' })).not.toBeInTheDocument()
  })

  it('инспектор без дашборда попадает в паспорта, а не на /home', async () => {
    vi.stubEnv('VITE_PASSPORT_ENABLED', 'true')
    vi.resetModules()
    const { ProtectedRoute: Fresh } = await import('../../App')
    const { useAuthStore: store } = await import('../../stores/authStore')
    store.setState({ user: { id: 1, roles: ['inspector'], actions: actionsFor(['inspector']) }, isAuthenticated: true, hydrating: false })
    render(
      <Routes>
        <Route path="/dashboard" element={<Fresh action="dashboard.use"><div>board</div></Fresh>} />
        <Route path="/dashboard/passports" element={<div>passports</div>} />
        <Route path="/home" element={<div>home</div>} />
      </Routes>,
      { routerEntries: ['/dashboard'] },
    )
    expect(await screen.findByText('passports')).toBeInTheDocument()
    vi.unstubAllEnvs()
    expect(ProtectedRoute).toBeDefined()
  })
})
