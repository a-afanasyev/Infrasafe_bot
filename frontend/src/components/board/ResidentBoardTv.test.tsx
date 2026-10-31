import { afterEach, describe, expect, it, vi } from 'vitest'
import { act, fireEvent, render, screen } from '../../test/test-utils'
import { defaultBoardConfig } from '../../types/boardConfig'
import ResidentBoardTv from './ResidentBoardTv'

const now = new Date('2026-10-11T20:10:30Z')
// completed_month — решённые за бизнес-месяц (как на главной жителей); сумма status_counts (55) на табло не показывается.
const data = { status_counts: { 'Новая': 14, 'Выполнена': 3, 'Принято': 2, 'Исполнено': 50 }, completed_month: 5, active_requests: [], active_executors: 0, avg_resolution_hours: null, avg_rating: null }
const props = { board: data, config: defaultBoardConfig, now, updatedAt: now.getTime(), isError: false, configError: false }
afterEach(() => vi.useRealTimers())

describe('TV board', () => {
  it('показывает completed_month, пустые метрики словами, выполнение и приёмку раздельно', () => {
    render(<ResidentBoardTv {...props} />)
    expect(screen.getByText('Ждёт приёмки')).toBeInTheDocument()
    expect(screen.getByText('Подтверждено')).toBeInTheDocument()
    expect(screen.getByText('5')).toBeInTheDocument()
    expect(screen.queryByText('55')).not.toBeInTheDocument()
    expect(screen.getAllByText('Нет данных').length).toBeGreaterThan(0)
    expect(screen.queryByText('—')).not.toBeInTheDocument()
  })
  it('без данных API и конфига не выдумывает цифры, объявления и QR', () => {
    render(<ResidentBoardTv {...props} board={undefined} config={undefined} updatedAt={0} isError configError />)
    expect(screen.getByText(/Данные временно недоступны/)).toBeInTheDocument()
    expect(screen.queryByText('Плановые работы')).not.toBeInTheDocument()
    expect(screen.queryByRole('img', { name: /QR-код/ })).not.toBeInTheDocument()
  })
  it('при ошибке опроса показывает время последних успешных данных', () => {
    render(<ResidentBoardTv {...props} now={new Date('2026-10-11T20:15:30Z')} isError />)
    expect(screen.getByText(/Обновление прервано · Обновлено в 01:10:30/)).toBeInTheDocument()
  })
  it('offline показывает обрыв сразу и сохраняет время последних данных', () => {
    render(<ResidentBoardTv {...props} />)
    fireEvent(window, new Event('offline'))
    expect(screen.getByText(/Обновление прервано · Обновлено в 01:10:30/)).toBeInTheDocument()
    fireEvent(window, new Event('online'))
    expect(screen.queryByText(/Обновление прервано/)).not.toBeInTheDocument()
  })
  it('зависший опрос считается устаревшим ещё до ошибки запроса', () => {
    render(<ResidentBoardTv {...props} now={new Date('2026-10-11T20:15:30Z')} />)
    expect(screen.getByText(/Обновление прервано/)).toBeInTheDocument()
  })
  it('уважает видимость модулей из конфигурации', () => {
    render(<ResidentBoardTv {...props} config={{ ...defaultBoardConfig, layout: [] }} />)
    expect(screen.queryByText('Текущие заявки')).not.toBeInTheDocument()
    expect(screen.queryByText('Важное для вас')).not.toBeInTheDocument()
    expect(screen.queryByText('Сводка заявок')).not.toBeInTheDocument()
  })
  it('объявления крутятся сами каждые 15 секунд, с паузой и ручным переключением', () => {
    vi.useFakeTimers()
    const [first] = defaultBoardConfig.announcements
    const config = { ...defaultBoardConfig, announcements: [
      { ...first, id: 'a1', title: { ru: 'Первое объявление', uz: '' }, text: { ru: 'Текст один', uz: '' } },
      { ...first, id: 'a2', title: { ru: 'Второе объявление', uz: '' }, text: { ru: 'Текст два', uz: '' } },
    ] }
    render(<ResidentBoardTv {...props} config={config} />)
    expect(screen.getByRole('heading', { name: 'Первое объявление' })).toBeInTheDocument()
    act(() => { vi.advanceTimersByTime(15_000) })
    expect(screen.getByRole('heading', { name: 'Второе объявление' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Приостановить смену объявлений' }))
    act(() => { vi.advanceTimersByTime(40_000) })
    expect(screen.getByRole('heading', { name: 'Второе объявление' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Следующее объявление' }))
    expect(screen.getByRole('heading', { name: 'Первое объявление' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Возобновить смену объявлений' })).toBeInTheDocument()
  })
  it('QR бота строится локально и ведёт на t.me', () => {
    render(<ResidentBoardTv {...props} config={{ ...defaultBoardConfig, bot: { ...defaultBoardConfig.bot, username: 'profkbot' } }} />)
    const image = screen.getByRole('img', { name: 'QR-код: Telegram-бот @profkbot' })
    expect(image.tagName.toLowerCase()).toBe('svg')
    expect(image.closest('a')).toHaveAttribute('href', 'https://t.me/profkbot')
  })
})
