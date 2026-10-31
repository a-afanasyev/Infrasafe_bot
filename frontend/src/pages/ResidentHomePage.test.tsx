import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { act, fireEvent, render, screen, waitFor, within } from '../test/test-utils'
import { testI18n } from '../test/test-utils'
import { server } from '../test/msw/server'
import { defaultBoardConfig, defaultHomeConfig } from '../types/boardConfig'
import type { AnnouncementCfg, BoardConfigData, HomeBlockCfg, PlannedWorkCfg } from '../types/boardConfig'
import { makeTwoYardsData, servePublicElevators } from '../test/fixtures/publicElevators'
import NoticeCarousel, { SLIDE_INTERVAL_MS } from '../components/home/NoticeCarousel'
import ResidentHomePage from './ResidentHomePage'

// Страница жителей: данные — конфиг витрины (configOverride) + анонимные
// агрегаты публичного табло (msw). «Сегодня» фиксировано: 2026-10-11 12:00 Ташкент.

const EMPTY = { ru: '', uz: '' }

function work(id: string, date: string, title: string, extra: Partial<PlannedWorkCfg> = {}): PlannedWorkCfg {
  return { id, date, time_from: '10:00', time_to: '12:00', title: { ru: title, uz: title }, place: EMPTY, text: EMPTY, ...extra }
}

function announcement(id: string, title: string, extra: Partial<AnnouncementCfg> = {}): AnnouncementCfg {
  return {
    id, icon: '📢', important: false, title: { ru: title, uz: title },
    text: { ru: `Текст ${title}`, uz: '' }, published_at: '2026-10-10T09:00', ...extra,
  }
}

function config(overrides: Partial<BoardConfigData> = {}): BoardConfigData {
  const cfg = JSON.parse(JSON.stringify(defaultBoardConfig)) as BoardConfigData
  cfg.org.name = { ru: 'Pro Facility Kommunal', uz: 'Pro Facility Kommunal' }
  cfg.contacts.dispatch_phone = '+998 78 333 19 71 '
  cfg.bot.username = 'profkbot'
  cfg.announcements = [announcement('a1', 'Сезонная уборка двора', { important: true })]
  cfg.planned_works = [
    work('past', '2026-10-01', 'Прошедшая работа'),
    work('late', '2026-10-16', 'Осмотр освещения', { time_from: '14:00', time_to: '16:00' }),
    work('soon', '2026-10-15', 'Уборка территории', {
      place: { ru: 'Двор и дорожки', uz: '' },
      text: { ru: 'Просим не парковаться у подъездов.', uz: '' },
    }),
  ]
  return { ...cfg, ...overrides }
}

const BOARD = {
  status_counts: { 'Новая': 3, 'В работе': 5, 'Закуп': 2, 'Уточнение': 1, 'Принято': 90 },
  active_requests: [],
  active_executors: 4,
  avg_resolution_hours: 5,
  avg_rating: 4.5,
  completed_month: 24,
  category_counts: {
    new: { plumbing: 2, 'Электрика': 1 },
    in_progress: { cleaning: 8 },
    completed_month: {},
  },
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(new Date('2026-10-11T07:00:00Z'))
  server.use(http.get('*/api/v2/public/board', () => HttpResponse.json(BOARD)))
})

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllEnvs()
  void testI18n.changeLanguage('ru')
})

function withHome(blocks: (b: HomeBlockCfg) => HomeBlockCfg, texts: Partial<BoardConfigData['home']> = {}): BoardConfigData {
  return config({ home: { ...defaultHomeConfig, ...texts, blocks: defaultHomeConfig.blocks.map(blocks) } })
}

describe('ResidentHomePage', () => {
  it('шапка, заголовок, контакты из конфига витрины', async () => {
    render(<ResidentHomePage configOverride={config()} />)
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Ваш дом сегодня')
    expect(screen.getAllByText('Pro Facility Kommunal').length).toBeGreaterThan(0)
    expect(screen.getByText('12:00')).toBeInTheDocument()
    expect(screen.getByText(/11 октября, вс/)).toBeInTheDocument()

    expect(screen.getByRole('link', { name: /\+998 78 333 19 71/ })).toHaveAttribute('href', 'tel:+998783331971')
    const botLinks = screen.getAllByRole('link').filter((a) => a.getAttribute('href') === 'https://t.me/profkbot')
    expect(botLinks.length).toBe(3)
    expect(screen.getByRole('img', { name: 'QR-код: Telegram-бот @profkbot' })).toBeInTheDocument()
    expect(screen.getByText('Пн–Пт 08:00–20:00 · Сб 09:00–17:00 · Вс 10:00–16:00')).toBeInTheDocument()
  })

  it('«Для экрана» ведёт на табло', () => {
    render(<ResidentHomePage configOverride={config()} />)
    expect(screen.getByRole('link', { name: /Для экрана/ })).toHaveAttribute('href', '/resident-board?mode=tv')
  })

  it('счётчики обращений и разбивка по категориям по нажатию', async () => {
    render(<ResidentHomePage configOverride={config()} />)
    const card = screen.getByRole('heading', { name: 'Обращения по комплексу' }).closest('section') as HTMLElement
    const newBtn = await within(card).findByRole('button', { name: /Новые\s*3/ })
    expect(within(card).getByRole('button', { name: /В работе\s*8/ })).toBeInTheDocument()
    expect(within(card).getByRole('button', { name: /Решено за месяц\s*24/ })).toBeInTheDocument()
    expect(within(card).getByText('Октябрь · сводка по комплексу')).toBeInTheDocument()

    fireEvent.click(newBtn)
    expect(newBtn).toHaveAttribute('aria-pressed', 'true')
    expect(within(card).getByText('Сантехника — 2 · Электрика — 1')).toBeInTheDocument()

    fireEvent.click(within(card).getByRole('button', { name: /Решено за месяц/ }))
    expect(within(card).getByText('В этой группе сейчас пусто')).toBeInTheDocument()

    fireEvent.click(within(card).getByRole('button', { name: 'Показать все обращения' }))
    expect(within(card).getByText('Октябрь · сводка по комплексу')).toBeInTheDocument()
  })

  it('старый бэкенд без completed_month — прочерк, а не ноль', async () => {
    const legacy: Record<string, unknown> = { ...BOARD }
    delete legacy.completed_month
    delete legacy.category_counts
    server.use(http.get('*/api/v2/public/board', () => HttpResponse.json(legacy)))
    render(<ResidentHomePage configOverride={config()} />)
    const card = screen.getByRole('heading', { name: 'Обращения по комплексу' }).closest('section') as HTMLElement
    await within(card).findByRole('button', { name: /Новые\s*3/ })
    expect(within(card).getByRole('button', { name: /Решено за месяц\s*—/ })).toBeInTheDocument()
  })

  it('ближайшие работы: без прошедших, по дате; подробности в модалке', async () => {
    render(<ResidentHomePage configOverride={config()} />)
    const card = screen.getByRole('heading', { name: 'Ближайшие работы' }).closest('section') as HTMLElement
    const rows = within(card).getAllByRole('button')
    expect(rows.map((r) => r.getAttribute('aria-label'))).toEqual([
      'Подробнее о работе: Уборка территории',
      'Подробнее о работе: Осмотр освещения',
    ])
    expect(within(rows[0]).getByText('15')).toBeInTheDocument()
    expect(within(rows[0]).getByText('10:00–12:00 · Двор и дорожки')).toBeInTheDocument()

    fireEvent.click(rows[0])
    const dialog = screen.getByRole('dialog')
    expect(within(dialog).getByRole('heading', { name: 'Уборка территории' })).toBeInTheDocument()
    expect(within(dialog).getByText('15 октября · 10:00–12:00 · Двор и дорожки')).toBeInTheDocument()
    expect(within(dialog).getByText('Просим не парковаться у подъездов.')).toBeInTheDocument()

    fireEvent.keyDown(document, { key: 'Escape' })
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  })

  it('нет работ и объявлений — честные пустые состояния', () => {
    render(<ResidentHomePage configOverride={config({ planned_works: [], announcements: [] })} />)
    expect(screen.getByText('Плановых работ пока нет')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Всё спокойно' })).toBeInTheDocument()
  })

  it('объявление открывается в модалке с полным текстом', () => {
    render(<ResidentHomePage configOverride={config()} />)
    expect(screen.getByText('Важно')).toBeInTheDocument()
    expect(screen.getByText('10 октября · 09:00')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Читать объявление/ }))
    const dialog = screen.getByRole('dialog')
    expect(within(dialog).getByText('Текст Сезонная уборка двора')).toBeInTheDocument()
    fireEvent.click(within(dialog).getByRole('button', { name: 'Понятно' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('переключатель языка: UZ', async () => {
    render(<ResidentHomePage configOverride={config()} />)
    fireEvent.click(screen.getByRole('button', { name: 'UZ' }))
    expect(await screen.findByRole('heading', { level: 1 })).toHaveTextContent('Uyingiz bugun')
    expect(screen.getByRole('button', { name: 'UZ' })).toHaveAttribute('aria-pressed', 'true')
  })
})

describe('ResidentHomePage — настройки страницы из редактора витрины', () => {
  it('название комплекса в шапке, свои заголовок, надпись и подпись', () => {
    render(<ResidentHomePage configOverride={withHome((b) => b, {
      complex_name: { ru: 'ЖК Olmazor Business City', uz: '' },
      title: { ru: 'Наш комплекс сегодня', uz: '' },
      eyebrow: { ru: 'Для жителей Olmazor', uz: '' },
      tagline: { ru: 'Всегда рядом.', uz: '' },
    })} />)
    expect(screen.getByText('Ваш жилой комплекс')).toBeInTheDocument()
    expect(screen.getByText('ЖК Olmazor Business City')).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Наш комплекс сегодня')
    expect(screen.getByText('Для жителей Olmazor')).toBeInTheDocument()
    expect(screen.getByText(/Всегда рядом\./)).toBeInTheDocument()
  })

  it('без названия комплекса — блока в шапке нет', () => {
    render(<ResidentHomePage configOverride={config()} />)
    expect(screen.queryByText('Ваш жилой комплекс')).not.toBeInTheDocument()
  })

  it('скрытый блок не рендерится, свой заголовок блока заменяет стандартный', () => {
    render(<ResidentHomePage configOverride={withHome((b) =>
      b.id === 'works' ? { ...b, visible: false }
        : b.id === 'requests' ? { ...b, title: { ru: 'Заявки жителей ЖК', uz: '' } } : b,
    )} />)
    expect(screen.queryByRole('heading', { name: 'Ближайшие работы' })).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Заявки жителей ЖК' })).toBeInTheDocument()
  })

  it('«Лифты»: сводка, неработающие, ссылка на полный список', async () => {
    vi.stubEnv('VITE_ELEVATORS_ENABLED', 'true')
    servePublicElevators(makeTwoYardsData())
    render(<ResidentHomePage configOverride={config()} />)
    const card = screen.getByRole('heading', { name: 'Лифты' }).closest('section') as HTMLElement
    expect(await within(card).findByText('работают')).toBeInTheDocument()
    expect(within(card).getByText('/ 5', { exact: false })).toBeInTheDocument()
    expect(within(card).getByText('ул. Мира, д. 3, подъезд 1, лифт 1')).toBeInTheDocument()
    expect(within(card).getByRole('link', { name: /Все лифты/ })).toHaveAttribute('href', '/elevators')
  })

  it('модуль лифтов выключен — блока нет, даже если он видим в конфиге', () => {
    vi.stubEnv('VITE_ELEVATORS_ENABLED', '')
    render(<ResidentHomePage configOverride={config()} />)
    expect(screen.queryByRole('heading', { name: 'Лифты' })).not.toBeInTheDocument()
  })

  it('«Отчёты о работах»: свежие отчёты и ссылка на архив', async () => {
    vi.stubEnv('VITE_WORK_REPORTS_ENABLED', 'true')
    server.use(http.get('*/api/v2/public/work-reports', () => HttpResponse.json({
      items: [{ id: 7, category_key: 'plumbing', address: 'ул. Мира, д. 3', completed_on: '2026-10-09', before: [1], after: [2] }],
      total: 1, limit: 24, offset: 0,
    })))
    render(<ResidentHomePage configOverride={config()} />)
    const card = screen.getByRole('heading', { name: 'Отчёты о работах' }).closest('section') as HTMLElement
    expect(await within(card).findByText('Сантехника')).toBeInTheDocument()
    expect(within(card).getByText('09.10.2026 · ул. Мира, д. 3')).toBeInTheDocument()
    expect(within(card).getAllByRole('link').map((a) => a.getAttribute('href'))).toEqual(['/work-reports', '/work-reports/7'])
  })
})

describe('NoticeCarousel', () => {
  const list = [announcement('a1', 'Первое'), announcement('a2', 'Второе'), announcement('a3', 'Третье')]

  afterEach(() => vi.useRealTimers())

  it('листается кнопками и точками, по кругу', () => {
    render(<NoticeCarousel announcements={list} lang="ru" onOpen={() => {}} />)
    expect(screen.getByRole('heading', { name: 'Первое' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Предыдущее объявление' }))
    expect(screen.getByRole('heading', { name: 'Третье' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Следующее объявление' }))
    expect(screen.getByRole('heading', { name: 'Первое' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Объявление 2' }))
    expect(screen.getByRole('heading', { name: 'Второе' })).toBeInTheDocument()
    expect(screen.getByText('/ 03')).toBeInTheDocument()
  })

  it('сменяется сам и останавливается паузой', () => {
    vi.useFakeTimers()
    render(<NoticeCarousel announcements={list} lang="ru" onOpen={() => {}} />)
    act(() => { vi.advanceTimersByTime(SLIDE_INTERVAL_MS) })
    expect(screen.getByRole('heading', { name: 'Второе' })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Приостановить смену объявлений' }))
    act(() => { vi.advanceTimersByTime(SLIDE_INTERVAL_MS * 3) })
    expect(screen.getByRole('heading', { name: 'Второе' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Возобновить смену объявлений' })).toHaveAttribute('aria-pressed', 'true')
  })

  it('одно объявление — без управления каруселью', () => {
    render(<NoticeCarousel announcements={[list[0]]} lang="ru" onOpen={() => {}} />)
    expect(screen.queryByRole('button', { name: 'Следующее объявление' })).not.toBeInTheDocument()
  })
})
