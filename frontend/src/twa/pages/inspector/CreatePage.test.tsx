import { describe, it, expect, beforeEach, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
import { fireEvent, render, screen, waitFor } from '../../../test/test-utils'
import InspectorCreatePage from './CreatePage'

// TEST-068: мастер обходчика — двор → дом → категория → описание → срочность →
// фото → подтверждение. Заявка уходит в POST /requests/inspector как
// building-level, после успеха форма сбрасывается (остаёмся на /twa/inspector).

const { mockGet, mockPost, mockPatch, toastMock } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockPost: vi.fn(),
  mockPatch: vi.fn(),
  toastMock: { success: vi.fn(), warning: vi.fn(), error: vi.fn() },
}))

vi.mock('../../twaClient', () => ({
  twaClient: { get: mockGet, post: mockPost, patch: mockPatch },
}))
vi.mock('sonner', () => ({ toast: toastMock }))
// canvas в jsdom нет — даунскейл возвращает файл как есть.
vi.mock('../../utils/downscaleImage', () => ({ downscaleImage: (f: File) => Promise.resolve(f) }))

const YARDS = [{ id: 1, name: 'Двор Север' }, { id: 2, name: 'Двор Юг' }]
const BUILDINGS_1 = [{ id: 12, address: 'ул. Ленина, 1' }]

function mockApi() {
  mockGet.mockImplementation((url: string) => {
    if (url === '/api/v2/addresses/yards') return Promise.resolve({ data: YARDS })
    if (url === '/api/v2/addresses/yards/1/buildings') return Promise.resolve({ data: BUILDINGS_1 })
    if (url === '/api/v2/addresses/yards/2/buildings') return Promise.resolve({ data: [] })
    if (url === '/api/v2/profile') return Promise.resolve({ data: { roles: ['inspector'], active_role: 'inspector' } })
    return Promise.reject(new Error(`unexpected GET ${url}`))
  })
  mockPost.mockImplementation((url: string) => {
    if (url === '/api/v2/requests/inspector') return Promise.resolve({ data: { request_number: '260918-001' } })
    if (url === '/api/v2/media/upload') return Promise.resolve({ data: { ok: true } })
    return Promise.reject(new Error(`unexpected POST ${url}`))
  })
}

beforeEach(() => {
  mockGet.mockReset()
  mockPost.mockReset()
  mockPatch.mockReset()
  toastMock.success.mockReset()
  toastMock.warning.mockReset()
  toastMock.error.mockReset()
  sessionStorage.clear()
  mockApi()
})

async function walkToConfirm(user: ReturnType<typeof userEvent.setup>, text = 'Разбит фонарь') {
  await user.click(await screen.findByRole('button', { name: /Двор Север/ }))
  await user.click(await screen.findByRole('button', { name: /ул\. Ленина, 1/ }))
  await user.click(screen.getByRole('button', { name: 'Электрика' }))
  await user.type(screen.getByRole('textbox'), text)
  await user.click(screen.getByRole('button', { name: 'Далее' }))
  await user.click(screen.getByRole('button', { name: 'Срочная' }))
  expect(screen.getByText('Добавить фото')).toBeInTheDocument()
}

describe('InspectorCreatePage — мастер', () => {
  it('полный проход: POST /requests/inspector с address_type=building и сброс формы после успеха', async () => {
    const user = userEvent.setup()
    render(<InspectorCreatePage />)
    await walkToConfirm(user)
    await user.click(screen.getByRole('button', { name: 'Далее' })) // фото — пропускаем

    expect(screen.getByText('Подтверждение')).toBeInTheDocument()
    expect(screen.getByText(/ул\. Ленина, 1/)).toBeInTheDocument()
    expect(screen.getByText(/Разбит фонарь/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Отправить заявку' }))

    await waitFor(() => expect(mockPost).toHaveBeenCalledTimes(1))
    expect(mockPost).toHaveBeenCalledWith('/api/v2/requests/inspector', {
      category: 'electricity',
      address_type: 'building',
      address_id: 12,
      description: 'Разбит фонарь',
      urgency: 'high',
    })
    expect(toastMock.success).toHaveBeenCalledWith('Заявка создана')
    // Форма сброшена: снова шаг «двор», черновик стёрт.
    expect(await screen.findByText('Выберите двор')).toBeInTheDocument()
    const draft = JSON.parse(sessionStorage.getItem('twa.create.inspector.draft') ?? '{}')
    expect(draft).toMatchObject({ step: 0, yardId: null, buildingId: null, description: '' })
  })

  it('«Далее» на шаге описания заблокировано, пока текст пустой', async () => {
    const user = userEvent.setup()
    render(<InspectorCreatePage />)
    await user.click(await screen.findByRole('button', { name: /Двор Север/ }))
    await user.click(await screen.findByRole('button', { name: /ул\. Ленина, 1/ }))
    await user.click(screen.getByRole('button', { name: 'Электрика' }))
    expect(screen.getByRole('button', { name: 'Далее' })).toBeDisabled()
    await user.type(screen.getByRole('textbox'), '   ')
    expect(screen.getByRole('button', { name: 'Далее' })).toBeDisabled()
  })

  it('двор без домов показывает подсказку; «← Назад» возвращает к дворам', async () => {
    const user = userEvent.setup()
    render(<InspectorCreatePage />)
    await user.click(await screen.findByRole('button', { name: /Двор Юг/ }))
    expect(await screen.findByText('В этом дворе нет активных домов')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /← Назад/ }))
    expect(await screen.findByRole('button', { name: /Двор Север/ })).toBeInTheDocument()
  })

  it('пустой список дворов → «Нет активных дворов»', async () => {
    mockGet.mockImplementation((url: string) =>
      url === '/api/v2/addresses/yards' ? Promise.resolve({ data: [] }) : Promise.resolve({ data: {} }),
    )
    render(<InspectorCreatePage />)
    expect(await screen.findByText('Нет активных дворов')).toBeInTheDocument()
  })

  it('фото: загружаются после создания заявки, сбой одного файла — предупреждение, заявка не откатывается', async () => {
    mockPost.mockImplementation((url: string, body: unknown) => {
      if (url === '/api/v2/requests/inspector') return Promise.resolve({ data: { request_number: '260918-002' } })
      if (url === '/api/v2/media/upload') {
        const name = (body as FormData).get('file') instanceof File ? ((body as FormData).get('file') as File).name : ''
        return name === 'bad.jpg' ? Promise.reject(new Error('413')) : Promise.resolve({ data: {} })
      }
      return Promise.reject(new Error(`unexpected POST ${url}`))
    })
    const user = userEvent.setup()
    const { container } = render(<InspectorCreatePage />)
    await walkToConfirm(user)

    const gallery = container.querySelectorAll('input[type="file"]')[1] as HTMLInputElement
    const good = new File(['a'], 'good.jpg', { type: 'image/jpeg' })
    const bad = new File(['b'], 'bad.jpg', { type: 'image/jpeg' })
    fireEvent.change(gallery, { target: { files: [good, bad] } })
    await user.click(screen.getByRole('button', { name: 'Далее' }))

    expect(screen.getByText('2')).toBeInTheDocument() // счётчик фото в подтверждении
    await user.click(screen.getByRole('button', { name: 'Отправить заявку' }))

    await waitFor(() => expect(toastMock.warning).toHaveBeenCalledWith('Заявка создана, не загрузились фото №2'))
    const uploads = mockPost.mock.calls.filter(([url]) => url === '/api/v2/media/upload')
    expect(uploads).toHaveLength(2)
    const form = uploads[0][1] as FormData
    expect(form.get('request_number')).toBe('260918-002')
    expect(form.get('category')).toBe('request_photo')
    expect(uploads[0][2]).toMatchObject({ timeout: 60_000 })
    expect(toastMock.success).not.toHaveBeenCalled()
  })

  it('ошибка сервера: detail-массив (422) рендерится в блоке ошибки, форма не сбрасывается', async () => {
    mockPost.mockRejectedValue({
      message: 'Request failed',
      response: { status: 422, data: { detail: [{ loc: ['body', 'description'], msg: 'too short' }] } },
    })
    const user = userEvent.setup()
    render(<InspectorCreatePage />)
    await walkToConfirm(user)
    await user.click(screen.getByRole('button', { name: 'Далее' }))
    await user.click(screen.getByRole('button', { name: 'Отправить заявку' }))

    expect(await screen.findByText('body.description: too short')).toBeInTheDocument()
    expect(toastMock.error).toHaveBeenCalled()
    expect(screen.getByText('Подтверждение')).toBeInTheDocument()
  })

  it('черновик из sessionStorage восстанавливает шаг и выбранный адрес', async () => {
    sessionStorage.setItem('twa.create.inspector.draft', JSON.stringify({
      step: 6, yardId: 1, buildingId: 12, buildingLabel: 'ул. Ленина, 1',
      category: 'plumbing', description: 'Течёт стояк', urgency: 'critical',
    }))
    const user = userEvent.setup()
    render(<InspectorCreatePage />)
    expect(await screen.findByText('Подтверждение')).toBeInTheDocument()
    expect(screen.getByText(/Течёт стояк/)).toBeInTheDocument()
    expect(screen.getByText(/Критическая/)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Отправить заявку' }))
    await waitFor(() => expect(mockPost).toHaveBeenCalledWith('/api/v2/requests/inspector', expect.objectContaining({
      category: 'plumbing', address_id: 12, urgency: 'critical',
    })))
  })
})
