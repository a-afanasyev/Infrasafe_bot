import { describe, it, expect, beforeEach, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { render, screen, waitFor, within, fireEvent } from '../test/test-utils'
import { server } from '../test/msw/server'
import { defaultBoardConfig } from '../types/boardConfig'
import type { BoardConfigData } from '../types/boardConfig'
import BoardEditorPage from './BoardEditorPage'

// TEST-068: редактор витрины. Черновик сеется из серверного конфига, правки
// живут только в draft, «Сохранить» шлёт PUT без display_tz, «Сбросить»
// возвращает серверные значения, несохранённые правки ставят beforeunload-guard.

const toastMock = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }))
vi.mock('sonner', () => ({ toast: toastMock }))

function serverConfig(): BoardConfigData & { display_tz: string } {
  const cfg = JSON.parse(JSON.stringify(defaultBoardConfig)) as BoardConfigData
  cfg.org.name = { ru: 'УК Пример', uz: 'BK Namuna' }
  cfg.bot.username = 'example_bot'
  return { ...cfg, display_tz: 'Asia/Tashkent' }
}

const MODULE_LABELS: Record<string, string> = {
  stats: 'Сводка', requests: 'Текущие заявки', announcements: 'Объявления', rating: 'Оценка жителей',
  hours: 'Часы работы', workreports: 'Отчёты о работах', elevators: 'Лифты',
}

let putBodies: Array<Record<string, unknown>>

beforeEach(() => {
  putBodies = []
  toastMock.success.mockReset()
  toastMock.error.mockReset()
  server.use(
    http.get('*/api/v2/public/board-config', () => HttpResponse.json(serverConfig())),
    http.put('*/api/v2/board-config', async ({ request }) => {
      const body = (await request.json()) as Record<string, unknown>
      putBodies.push(body)
      return HttpResponse.json({ ...body, display_tz: 'Asia/Tashkent' })
    }),
  )
})

function section(title: string): HTMLElement {
  const h = screen.getByRole('heading', { level: 3, name: title })
  return h.closest('section') as HTMLElement
}

/** RU-поле LocalizedField по подписи внутри секции. */
function ruField(sec: HTMLElement, label: string): HTMLInputElement {
  const labelEl = within(sec).getByText(label)
  return within(labelEl.parentElement as HTMLElement).getByPlaceholderText('RU') as HTMLInputElement
}

async function renderReady() {
  render(<BoardEditorPage />)
  await waitFor(() => expect(screen.getByRole('heading', { level: 3, name: 'Контакты' })).toBeInTheDocument())
}

describe('BoardEditorPage', () => {
  it('до прихода конфига — «Загрузка...», затем черновик посеян серверными значениями', async () => {
    render(<BoardEditorPage />)
    expect(screen.getByText('Загрузка...')).toBeInTheDocument()
    await waitFor(() => expect(screen.getByRole('heading', { level: 3, name: 'Контакты' })).toBeInTheDocument())
    expect(ruField(section('Управляющая компания'), 'Наименование').value).toBe('УК Пример')
    expect(screen.getByDisplayValue('example_bot')).toBeInTheDocument()
    // Все модули из layout перечислены под своими подписями.
    const modules = section('Блоки страницы')
    for (const l of defaultBoardConfig.layout) {
      expect(within(modules).getByText(MODULE_LABELS[l.id])).toBeInTheDocument()
    }
  })

  it('правка наименования → PUT /api/v2/board-config с новым значением и без display_tz', async () => {
    await renderReady()
    const name = ruField(section('Управляющая компания'), 'Наименование')
    fireEvent.change(name, { target: { value: 'УК Новая' } })
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить' }))

    await waitFor(() => expect(putBodies).toHaveLength(1))
    expect(putBodies[0]).not.toHaveProperty('display_tz')
    expect(putBodies[0].org).toEqual({ name: { ru: 'УК Новая', uz: 'BK Namuna' }, subtitle: defaultBoardConfig.org.subtitle })
    await waitFor(() => expect(toastMock.success).toHaveBeenCalledWith('Витрина сохранена'))
  })

  it('видимость и ширина модуля переключаются и уходят в layout', async () => {
    await renderReady()
    const modules = section('Блоки страницы')
    const statsRow = within(modules).getByText('Сводка').closest('div') as HTMLElement
    const visible = within(statsRow).getByRole('checkbox') as HTMLInputElement
    expect(visible.checked).toBe(true)
    fireEvent.click(visible)
    // Ширина: full → half (кнопка подписана текущим состоянием).
    fireEvent.click(within(statsRow).getByRole('button', { name: 'На всю ширину' }))
    expect(within(statsRow).getByRole('button', { name: 'Половина ширины (в ряд с соседом)' })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Сохранить' }))
    await waitFor(() => expect(putBodies).toHaveLength(1))
    const layout = putBodies[0].layout as Array<{ id: string; visible: boolean; width: string }>
    expect(layout.find((l) => l.id === 'stats')).toEqual({ id: 'stats', visible: false, width: 'half' })
  })

  it('объявления: добавить → заполнить → важное; удалить — исчезает из PUT', async () => {
    await renderReady()
    const ann = section('Объявления')
    const before = within(ann).getAllByRole('button', { name: 'remove' }).length
    fireEvent.click(within(ann).getByRole('button', { name: 'Добавить объявление' }))
    expect(within(ann).getAllByRole('button', { name: 'remove' })).toHaveLength(before + 1)

    // Последний блок — новый: заполняем заголовок и ставим «Важное».
    const blocks = within(ann).getAllByRole('button', { name: 'remove' }).map((b) => b.closest('.rounded-sm') as HTMLElement)
    const fresh = blocks[blocks.length - 1]
    const titleRu = within(fresh).getAllByPlaceholderText('RU')[0]
    fireEvent.change(titleRu, { target: { value: 'Отключение воды' } })
    fireEvent.click(within(fresh).getByLabelText('Важное'))

    // Удаляем первое (дефолтное) объявление.
    fireEvent.click(within(blocks[0]).getByRole('button', { name: 'remove' }))
    expect(within(ann).getAllByRole('button', { name: 'remove' })).toHaveLength(before)

    fireEvent.click(screen.getByRole('button', { name: 'Сохранить' }))
    await waitFor(() => expect(putBodies).toHaveLength(1))
    const sent = putBodies[0].announcements as Array<{ id: string; important: boolean; title: { ru: string } }>
    expect(sent.map((a) => a.id)).not.toContain('default-planned-works')
    expect(sent[sent.length - 1]).toMatchObject({ important: true, title: { ru: 'Отключение воды' } })
  })

  it('часы работы: «Выходной» блокирует время; username бота теряет ведущий @', async () => {
    await renderReady()
    const hours = section('Часы работы')
    const monRow = within(hours).getByText('Пн').closest('div') as HTMLElement
    const [open, close] = within(monRow).getAllByDisplayValue(/^\d\d:\d\d$/) as HTMLInputElement[]
    expect(open).toBeEnabled()
    fireEvent.click(within(monRow).getByLabelText('Выходной'))
    expect(open).toBeDisabled()
    expect(close).toBeDisabled()

    const bot = screen.getByDisplayValue('example_bot')
    fireEvent.change(bot, { target: { value: '@new_bot' } })
    expect(screen.getByDisplayValue('new_bot')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Сохранить' }))
    await waitFor(() => expect(putBodies).toHaveLength(1))
    const wh = putBodies[0].working_hours as Array<{ day: string; closed: boolean }>
    expect(wh.find((w) => w.day === 'mon')?.closed).toBe(true)
    expect((putBodies[0].bot as { username: string }).username).toBe('new_bot')
  })

  it('«Сбросить» возвращает серверные значения; beforeunload-guard только при несохранённых правках', async () => {
    await renderReady()
    const fireUnload = () => {
      const ev = new Event('beforeunload', { cancelable: true })
      window.dispatchEvent(ev)
      return ev.defaultPrevented
    }
    expect(fireUnload()).toBe(false)

    const phone = section('Контакты')
    const phoneInput = within(phone).getByDisplayValue(defaultBoardConfig.contacts.dispatch_phone)
    fireEvent.change(phoneInput, { target: { value: '+998 90 000-00-00' } })
    expect(fireUnload()).toBe(true)

    fireEvent.click(screen.getByRole('button', { name: 'Сбросить' }))
    expect(within(phone).getByDisplayValue(defaultBoardConfig.contacts.dispatch_phone)).toBeInTheDocument()
    expect(fireUnload()).toBe(false)
    expect(putBodies).toHaveLength(0)
  })

  it('ошибка сохранения → toast.error, черновик остаётся', async () => {
    server.use(http.put('*/api/v2/board-config', () => HttpResponse.json({ detail: 'nope' }, { status: 500 })))
    await renderReady()
    fireEvent.change(ruField(section('Управляющая компания'), 'Наименование'), { target: { value: 'Х' } })
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить' }))
    await waitFor(() => expect(toastMock.error).toHaveBeenCalledWith('Не удалось сохранить витрину', expect.anything()))
    expect(ruField(section('Управляющая компания'), 'Наименование').value).toBe('Х')
  })
})
