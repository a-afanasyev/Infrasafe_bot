import { describe, it, expect, beforeEach, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { render, screen, waitFor, within } from '../../test/test-utils'
import { server } from '../../test/msw/server'
import { apiClient } from '../../api/client'
import RequestDetailModal from './RequestDetailModal'

// useHasRole gates the manager-only urgency editor — mock it per test.
// useHasAnyRole гейтит RequestMaterialsBlock (склад) и загрузчик фотоотчёта;
// по умолчанию false (beforeEach), включается точечно в тестах фотоотчёта.
const mockHasRole = vi.fn()
const mockHasAnyRole = vi.fn()
vi.mock('../../hooks/useHasRole', () => ({
  useHasRole: (r: string) => mockHasRole(r),
  useHasAnyRole: (roles: readonly string[]) => mockHasAnyRole(roles),
}))

function noop() {}

function makeRequest(over: Record<string, unknown> = {}) {
  return {
    request_number: '260101-001',
    status: 'В работе',          // active (non-terminal) by default
    category: 'electricity',
    urgency: 'high',
    source: 'web',
    description: 'desc',
    address: 'addr',
    apartment_id: null,
    executor_id: null,
    executor_name: null,
    created_at: '2026-01-01T12:00:00Z',
    updated_at: null,
    manager_confirmed: false,
    ...over,
  }
}

function mockEndpoints(req: Record<string, unknown>) {
  server.use(
    http.get('*/api/v2/requests/:number/comments', () => HttpResponse.json([])),
    http.get('*/api/v2/requests/:number', () => HttpResponse.json(req)),
  )
}

async function renderModal(req: Record<string, unknown>) {
  mockEndpoints(req)
  render(<RequestDetailModal requestNumber={String(req.request_number)} onClose={noop} />)
  // Wait until the request data loaded (urgency badge text appears).
  await waitFor(() => expect(screen.getByText('Срочная')).toBeInTheDocument())
}

beforeEach(() => {
  mockHasRole.mockReset()
  mockHasAnyRole.mockReset()
  mockHasAnyRole.mockReturnValue(false)
})

describe('RequestDetailModal — manager urgency editor gating (TASK 17)', () => {
  it('manager + active status → urgency is an editable dropdown trigger', async () => {
    mockHasRole.mockReturnValue(true) // manager
    await renderModal(makeRequest({ urgency: 'high', status: 'В работе' }))
    // The editable variant renders a <button> trigger (DropdownMenu); badge-only is a <span>.
    expect(screen.getByRole('button', { name: /Срочная/ })).toBeInTheDocument()
  })

  it('non-manager → urgency is badge only (no dropdown)', async () => {
    mockHasRole.mockReturnValue(false) // executor/applicant
    await renderModal(makeRequest({ urgency: 'high', status: 'В работе' }))
    expect(screen.queryByRole('button', { name: /Срочная/ })).not.toBeInTheDocument()
    expect(screen.getByText('Срочная')).toBeInTheDocument()
  })

  it('manager + terminal status (Принято) → urgency badge only, frozen', async () => {
    mockHasRole.mockReturnValue(true)
    await renderModal(makeRequest({ urgency: 'high', status: 'Принято' }))
    expect(screen.queryByRole('button', { name: /Срочная/ })).not.toBeInTheDocument()
    expect(screen.getByText('Срочная')).toBeInTheDocument()
  })

  it('manager + terminal status (Отменена) → urgency badge only, frozen', async () => {
    mockHasRole.mockReturnValue(true)
    await renderModal(makeRequest({ urgency: 'high', status: 'Отменена' }))
    expect(screen.queryByRole('button', { name: /Срочная/ })).not.toBeInTheDocument()
  })

  it('dual-read: legacy-russian stored urgency still renders + stays editable for manager', async () => {
    mockHasRole.mockReturnValue(true)
    await renderModal(makeRequest({ urgency: 'Срочная', status: 'В работе' }))
    // tUrgency('Срочная') → 'Срочная' via dual-read; editable trigger present.
    expect(screen.getByRole('button', { name: /Срочная/ })).toBeInTheDocument()
  })
})

describe('RequestDetailModal — status dropdown «В работе» executor gating (FE-129)', () => {
  // Bug: выбор «В работе» из статус-дропдауна для заявки из «Закуп» без
  // исполнителя открывал модалку выбора исполнителя и слал executor_id →
  // backend 422 «manager_purchase_done: unexpected field 'executor_id'».
  // Модалка назначения нужна только при взятии из «Новая».
  async function selectStatus(req: Record<string, unknown>, target: string) {
    mockHasRole.mockReturnValue(true)
    let patchBody: unknown = null
    server.use(
      http.get('*/api/v2/requests/:number/comments', () => HttpResponse.json([])),
      http.get('*/api/v2/requests/:number', () => HttpResponse.json(req)),
      http.patch('*/api/v2/requests/:number', async ({ request }) => {
        patchBody = await request.json()
        return HttpResponse.json({ ...req, status: target })
      }),
    )
    render(<RequestDetailModal requestNumber={String(req.request_number)} onClose={noop} />)
    await waitFor(() => expect(screen.getByText('Срочная')).toBeInTheDocument())
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: new RegExp(String(req.status)) }))
    await user.click(await screen.findByRole('menuitem', { name: new RegExp(target) }))
    return () => patchBody
  }

  it('«Закуп» → «В работе» without executor: commits directly, no executor modal, no executor_id', async () => {
    const getBody = await selectStatus(
      makeRequest({ status: 'Закуп', executor_id: null, urgency: 'high' }),
      'В работе',
    )
    await waitFor(() => expect(getBody()).toEqual({ status: 'В работе' }))
    expect(screen.queryByText('Назначить исполнителя')).not.toBeInTheDocument()
  })

  it('«Новая» → «В работе» without executor: opens the executor modal (no direct PATCH)', async () => {
    const getBody = await selectStatus(
      makeRequest({ status: 'Новая', executor_id: null, urgency: 'high' }),
      'В работе',
    )
    expect(await screen.findByText('Назначить исполнителя')).toBeInTheDocument()
    expect(getBody()).toBeNull()
  })
})

describe('RequestDetailModal — фотоотчёт: загрузка менеджером + группировка', () => {
  // Минимальный JPEG-префикс: MediaThumb конвертирует blob в data: URL через
  // FileReader — телу достаточно быть валидным Blob'ом.
  const jpegBytes = new Uint8Array([0xff, 0xd8, 0xff])

  function mockMediaEndpoints(items: Array<Record<string, unknown>>) {
    server.use(
      http.get('*/api/v2/media/request/:number', () => HttpResponse.json(items)),
      http.get('*/api/v2/media/:id/file', () =>
        new HttpResponse(jpegBytes, { headers: { 'Content-Type': 'image/jpeg' } })),
      // RequestMaterialsBlock активируется тем же useHasAnyRole-моком.
      http.get('*/api/v2/materials/by-request/:number', () =>
        HttpResponse.json({ items: [], total_cost: 0 })),
    )
  }

  it('менеджер: секция «Фотоотчёт» с кнопкой добавления; категории разведены по секциям', async () => {
    mockHasRole.mockReturnValue(true)
    mockHasAnyRole.mockReturnValue(true)
    mockMediaEndpoints([
      { id: 1, file_type: 'photo', mime_type: 'image/jpeg', category: 'request_photo' },
      { id: 2, file_type: 'photo', mime_type: 'image/jpeg', category: 'completion_photo' },
    ])
    await renderModal(makeRequest({}))
    expect(await screen.findByText('Фото')).toBeInTheDocument()
    expect(screen.getByText('Фотоотчёт')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Добавить фото работ' })).toBeInTheDocument()
  })

  it('не-менеджер без медиа: раздела и кнопки нет', async () => {
    mockHasRole.mockReturnValue(false)
    mockHasAnyRole.mockReturnValue(false)
    mockMediaEndpoints([])
    await renderModal(makeRequest({}))
    expect(screen.queryByText('Фотоотчёт')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Добавить фото работ' })).not.toBeInTheDocument()
  })

  it('выбор файла шлёт FormData с category=completion_photo и инвалидирует список', async () => {
    mockHasRole.mockReturnValue(true)
    mockHasAnyRole.mockReturnValue(true)
    let listCalls = 0
    mockMediaEndpoints([])
    server.use(
      http.get('*/api/v2/media/request/:number', () => {
        listCalls += 1
        return HttpResponse.json([])
      }),
    )
    // Не msw: парсинг multipart-тела (request.formData) падает на CI-ноде
    // (undici AssertionError на jsdom-File). Шпион на apiClient.post видит
    // исходный FormData без сериализации — стабильно на любой ноде.
    const postSpy = vi.spyOn(apiClient, 'post').mockResolvedValue({ data: { id: 10 } } as never)
    try {
      await renderModal(makeRequest({}))
      await waitFor(() => expect(listCalls).toBeGreaterThan(0))
      const callsBeforeUpload = listCalls

      const input = screen.getByTestId('completion-upload-input')
      const file = new File([jpegBytes], 'work.jpg', { type: 'image/jpeg' })
      await userEvent.upload(input, file)

      await waitFor(() => expect(postSpy).toHaveBeenCalledTimes(1))
      const [url, form] = postSpy.mock.calls[0] as [string, FormData]
      expect(url).toBe('/api/v2/media/upload')
      expect(form.get('category')).toBe('completion_photo')
      expect(form.get('request_number')).toBe('260101-001')
      expect((form.get('file') as File).name).toBe('work.jpg')
      // Успешная загрузка инвалидирует ['request-media', number] → refetch.
      await waitFor(() => expect(listCalls).toBeGreaterThan(callsBeforeUpload))
    } finally {
      postSpy.mockRestore()
    }
  })
})

describe('RequestDetailModal — FE-07 per-request state reset', () => {
  it('clears the manager-note field when a different request opens (render-time reset, no remount)', async () => {
    mockHasRole.mockReturnValue(true)
    server.use(
      http.get('*/api/v2/requests/:number/comments', () => HttpResponse.json([])),
      http.get('*/api/v2/requests/:number', ({ params }) =>
        HttpResponse.json(makeRequest({ request_number: params.number, status: 'В работе' }))),
    )
    const { rerender } = render(
      <RequestDetailModal requestNumber="260101-001" onClose={noop} />,
    )
    await waitFor(() => expect(screen.getByText('Срочная')).toBeInTheDocument())

    const note = screen.getByPlaceholderText('Добавить заметку...')
    await userEvent.type(note, 'черновик')
    expect(note).toHaveValue('черновик')

    // Switch to a different request — state must reset without a key-remount.
    rerender(<RequestDetailModal requestNumber="260101-002" onClose={noop} />)
    await waitFor(() =>
      expect(screen.getByPlaceholderText('Добавить заметку...')).toHaveValue(''),
    )
  })
})

// ──────────────────────────────────────────────────────────────────────────
// Смена исполнителя из карточки
// ──────────────────────────────────────────────────────────────────────────
//
// До этого исполнитель в карточке был read-only текстом, и сменить его можно
// было только «от сотрудника» (Сотрудники → «Назначить заявку»). Статусы —
// те же, что пускает канон MANAGER_ASSIGN.

describe('смена исполнителя из карточки', () => {
  it('менеджер видит «Сменить» рядом с исполнителем в «В работе»', async () => {
    mockHasRole.mockReturnValue(true)
    await renderModal(makeRequest({
      status: 'В работе', executor_id: 5, executor_name: 'Иван Иванов',
    }))

    expect(screen.getByRole('button', { name: 'Сменить' })).toBeInTheDocument()
  })

  it('без исполнителя предлагает «Назначить», а не «Сменить»', async () => {
    mockHasRole.mockReturnValue(true)
    await renderModal(makeRequest({
      status: 'Новая', executor_id: null, executor_name: null,
    }))

    expect(screen.getByRole('button', { name: 'Назначить' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Сменить' })).not.toBeInTheDocument()
  })

  it.each(['Закуп', 'Уточнение', 'Выполнена', 'Исполнено', 'Отменена'])(
    'в статусе %s контрола нет — канон оттуда не пускает',
    async (status) => {
      mockHasRole.mockReturnValue(true)
      await renderModal(makeRequest({
        status, executor_id: 5, executor_name: 'Иван Иванов',
      }))

      expect(screen.queryByRole('button', { name: 'Сменить' })).not.toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Назначить' })).not.toBeInTheDocument()
    })

  it('не-менеджеру контрол не показывается', async () => {
    mockHasRole.mockReturnValue(false)
    await renderModal(makeRequest({
      status: 'В работе', executor_id: 5, executor_name: 'Иван Иванов',
    }))

    expect(screen.queryByRole('button', { name: 'Сменить' })).not.toBeInTheDocument()
    // сам исполнитель при этом виден
    expect(screen.getByText('Иван Иванов')).toBeInTheDocument()
  })
})


describe('RequestDetailModal — смена категории менеджером', () => {
  function categoryResponse(over: Record<string, unknown> = {}) {
    return {
      request: makeRequest({ category: 'plumbing' }),
      no_op: false,
      old_category: 'electricity',
      new_category: 'plumbing',
      specialization_changed: true,
      old_specialization: 'electrician',
      new_specialization: 'plumber',
      redispatched: false,
      executor_id: null,
      executor_name: null,
      executor_spec_mismatch: false,
      can_reassign: true,
      ...over,
    }
  }

  it('менеджер + активный статус → заголовок-категория это dropdown-кнопка', async () => {
    mockHasRole.mockReturnValue(true)
    await renderModal(makeRequest({ category: 'electricity', status: 'Новая' }))
    expect(screen.getByRole('button', { name: /Электрика/ })).toBeInTheDocument()
  })

  it('не-менеджер → категория только текстом', async () => {
    mockHasRole.mockReturnValue(false)
    await renderModal(makeRequest({ category: 'electricity', status: 'Новая' }))
    expect(screen.queryByRole('button', { name: /Электрика/ })).not.toBeInTheDocument()
    expect(screen.getByText('Электрика')).toBeInTheDocument()
  })

  it.each(['Принято', 'Отменена'])('терминальный статус %s → без dropdown', async (status) => {
    mockHasRole.mockReturnValue(true)
    await renderModal(makeRequest({ category: 'electricity', status }))
    expect(screen.queryByRole('button', { name: /Электрика/ })).not.toBeInTheDocument()
  })

  it('выбор другой категории → PATCH …/category с канон-ключом', async () => {
    mockHasRole.mockReturnValue(true)
    const patch = vi.spyOn(apiClient, 'patch').mockResolvedValue({ data: categoryResponse() })
    await renderModal(makeRequest({ category: 'electricity', status: 'Новая' }))

    await userEvent.click(screen.getByRole('button', { name: /Электрика/ }))
    await userEvent.click(await screen.findByRole('menuitem', { name: 'Сантехника' }))

    await waitFor(() => expect(patch).toHaveBeenCalledWith(
      '/api/v2/requests/260101-001/category', { category: 'plumbing' }))
    patch.mockRestore()
  })

  it('выбор той же категории → запрос не уходит', async () => {
    mockHasRole.mockReturnValue(true)
    const patch = vi.spyOn(apiClient, 'patch').mockResolvedValue({ data: categoryResponse() })
    await renderModal(makeRequest({ category: 'electricity', status: 'Новая' }))

    await userEvent.click(screen.getByRole('button', { name: /Электрика/ }))
    await userEvent.click(await screen.findByRole('menuitem', { name: 'Электрика' }))

    expect(patch).not.toHaveBeenCalled()
    patch.mockRestore()
  })

  it('несоответствие специализации в «В работе» → баннер и кнопка переназначения', async () => {
    mockHasRole.mockReturnValue(true)
    const patch = vi.spyOn(apiClient, 'patch').mockResolvedValue({
      data: categoryResponse({
        request: makeRequest({ category: 'plumbing', status: 'В работе', executor_id: 5, executor_name: 'Иван Иванов' }),
        executor_id: 5, executor_name: 'Иван Иванов',
        executor_spec_mismatch: true, can_reassign: true,
      }),
    })
    await renderModal(makeRequest({
      category: 'electricity', status: 'В работе', executor_id: 5, executor_name: 'Иван Иванов',
    }))

    await userEvent.click(screen.getByRole('button', { name: /Электрика/ }))
    await userEvent.click(await screen.findByRole('menuitem', { name: 'Сантехника' }))

    const banner = await screen.findByRole('alert')
    expect(banner).toHaveTextContent('Специализация текущего исполнителя не соответствует новой категории')
    expect(within(banner).getByRole('button', { name: 'Переназначить' })).toBeInTheDocument()
    patch.mockRestore()
  })

  it('несоответствие в «Закуп» → баннер без кнопки (канон не пускает переназначение)', async () => {
    mockHasRole.mockReturnValue(true)
    const patch = vi.spyOn(apiClient, 'patch').mockResolvedValue({
      data: categoryResponse({
        request: makeRequest({ category: 'plumbing', status: 'Закуп', executor_id: 5, executor_name: 'Иван Иванов' }),
        executor_id: 5, executor_name: 'Иван Иванов',
        executor_spec_mismatch: true, can_reassign: false,
      }),
    })
    await renderModal(makeRequest({
      category: 'electricity', status: 'Закуп', executor_id: 5, executor_name: 'Иван Иванов',
    }))

    await userEvent.click(screen.getByRole('button', { name: /Электрика/ }))
    await userEvent.click(await screen.findByRole('menuitem', { name: 'Сантехника' }))

    const banner = await screen.findByRole('alert')
    expect(within(banner).queryByRole('button', { name: 'Переназначить' })).not.toBeInTheDocument()
    patch.mockRestore()
  })
})
