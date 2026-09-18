import { describe, it, expect, beforeEach, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { toast } from 'sonner'
import { render, screen, waitFor } from '../../test/test-utils'
import { server } from '../../test/msw/server'
import type { MaterialCard } from '../../types/materials'
import MaterialFormDialog from './MaterialFormDialog'

// TEST-068 (порция materials): карточка материала — создание/правка. Реальные
// QueryClient/i18n/msw; проверяется тело запроса и закрытие только после успеха.

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }))

const EXISTING: MaterialCard = {
  id: 7, name: 'Кабель ВВГ', unit: 'm', category: 'Электрика', min_stock: '50.000',
  is_active: true, created_at: null,
}

beforeEach(() => vi.mocked(toast.success).mockClear())

describe('MaterialFormDialog — создание', () => {
  it('кнопка «Сохранить» заблокирована без названия; POST с trim и без пустых полей', async () => {
    const user = userEvent.setup()
    const bodies: unknown[] = []
    server.use(http.post('*/api/v2/materials', async ({ request }) => {
      bodies.push(await request.json())
      return HttpResponse.json({ ...EXISTING, id: 1 }, { status: 201 })
    }))
    const onClose = vi.fn()
    render(<MaterialFormDialog open material={null} onClose={onClose} />)

    expect(screen.getByText('Новый материал')).toBeInTheDocument()
    expect(screen.queryByLabelText('Активен')).not.toBeInTheDocument()
    const save = screen.getByRole('button', { name: 'Сохранить' })
    expect(save).toBeDisabled()

    await user.type(screen.getAllByRole('textbox')[0], '  Лампа  ')
    expect(save).toBeEnabled()
    await user.selectOptions(screen.getAllByRole('combobox')[0], 'pcs')
    await user.click(save)

    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1))
    expect(bodies).toEqual([{ name: 'Лампа', unit: 'pcs' }])
    expect(toast.success).toHaveBeenCalledWith('Материал создан')
  })

  it('ошибка сервера: диалог не закрывается, toast.error', async () => {
    const user = userEvent.setup()
    server.use(http.post('*/api/v2/materials', () =>
      HttpResponse.json({ detail: 'Материал с таким названием уже есть' }, { status: 409 })))
    const onClose = vi.fn()
    render(<MaterialFormDialog open material={null} onClose={onClose} />)

    await user.type(screen.getAllByRole('textbox')[0], 'Лампа')
    await user.click(screen.getByRole('button', { name: 'Сохранить' }))

    await waitFor(() => expect(toast.error).toHaveBeenCalled())
    expect(onClose).not.toHaveBeenCalled()
  })
})

describe('MaterialFormDialog — правка', () => {
  it('поля предзаполнены; PATCH /materials/{id} несёт все поля и is_active', async () => {
    const user = userEvent.setup()
    const calls: { url: string; body: unknown }[] = []
    server.use(http.patch('*/api/v2/materials/:id', async ({ request }) => {
      calls.push({ url: new URL(request.url).pathname, body: await request.json() })
      return HttpResponse.json(EXISTING)
    }))
    const onClose = vi.fn()
    render(<MaterialFormDialog open material={EXISTING} onClose={onClose} />)

    expect(screen.getByText('Материал')).toBeInTheDocument()
    const name = screen.getAllByRole('textbox')[0] as HTMLInputElement
    expect(name.value).toBe('Кабель ВВГ')
    expect((screen.getAllByRole('combobox')[0] as HTMLSelectElement).value).toBe('m')
    expect((screen.getAllByRole('combobox')[1] as HTMLSelectElement).value).toBe('Электрика')
    expect((screen.getByRole('spinbutton') as HTMLInputElement).value).toBe('50.000')
    const active = screen.getByRole('checkbox')
    expect(active).toBeChecked()

    await user.click(active)
    await user.clear(screen.getByRole('spinbutton'))
    await user.click(screen.getByRole('button', { name: 'Сохранить' }))

    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1))
    expect(calls).toEqual([{
      url: '/uk/api/v2/materials/7',
      body: { name: 'Кабель ВВГ', unit: 'm', category: 'Электрика', min_stock: null, is_active: false },
    }])
    expect(toast.success).toHaveBeenCalledWith('Материал обновлён')
  })

  it('нестандартная категория карточки остаётся выбираемой опцией', () => {
    render(<MaterialFormDialog open material={{ ...EXISTING, category: 'Редкое' }} onClose={() => {}} />)
    const category = screen.getAllByRole('combobox')[1] as HTMLSelectElement
    expect(category.value).toBe('Редкое')
    expect(screen.getByRole('option', { name: 'Редкое' })).toBeInTheDocument()
  })

  it('«Отмена» зовёт onClose без запросов', async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()
    render(<MaterialFormDialog open material={EXISTING} onClose={onClose} />)
    await user.click(screen.getByRole('button', { name: 'Отмена' }))
    expect(onClose).toHaveBeenCalledTimes(1)
  })
})
