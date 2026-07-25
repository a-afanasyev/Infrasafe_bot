import { describe, it, expect, beforeEach, vi } from 'vitest'
import { fireEvent } from '@testing-library/react'
import { render, screen } from '../../test/test-utils'
import WorkReportsModule from './WorkReportsModule'
import { publicWorkReportMediaUrl } from '../../hooks/usePublicWorkReports'
import type { PublicWorkReport, PublicWorkReportsPage } from '../../types/workReports'

// T10 — WorkReportsModule reads data via usePublicWorkReports() (no props),
// so we mock the hook the same way RegisterPage.test.tsx mocks
// useRegistration: vi.hoisted shared object + vi.mock returning it.
const { mockQuery } = vi.hoisted(() => ({
  mockQuery: { data: undefined as { pages: PublicWorkReportsPage[] } | undefined },
}))

vi.mock('../../hooks/usePublicWorkReports', async () => {
  const actual = await vi.importActual<typeof import('../../hooks/usePublicWorkReports')>(
    '../../hooks/usePublicWorkReports',
  )
  return {
    ...actual,
    usePublicWorkReports: () => mockQuery,
  }
})

function makeReport(over: Partial<PublicWorkReport> = {}): PublicWorkReport {
  return {
    id: 1,
    category_key: 'electricity',
    address: 'Дом 1, кв 5',
    completed_on: '2026-07-20',
    before: [10],
    after: [11],
    ...over,
  }
}

function makePage(items: PublicWorkReport[]): PublicWorkReportsPage {
  return { items, total: items.length, limit: 6, offset: 0 }
}

beforeEach(() => {
  mockQuery.data = undefined
})

describe('WorkReportsModule', () => {
  it('renders category chip, address, date, and before/after photo pair for a populated report', () => {
    mockQuery.data = { pages: [makePage([makeReport()])] }
    render(<WorkReportsModule />)

    expect(screen.getByText('Электрика')).toBeInTheDocument()
    expect(screen.getByText('Дом 1, кв 5')).toBeInTheDocument()
    expect(screen.getByText('20.07.2026')).toBeInTheDocument()

    const images = screen.getAllByRole('img')
    expect(images).toHaveLength(2)
  })

  it('renders nothing when the list is empty (query resolved with 0 items)', () => {
    mockQuery.data = { pages: [makePage([])] }
    const { container } = render(<WorkReportsModule />)
    expect(container.firstChild).toBeNull()
  })

  it('renders nothing while the query has not resolved yet (data undefined)', () => {
    mockQuery.data = undefined
    const { container } = render(<WorkReportsModule />)
    expect(container.firstChild).toBeNull()
  })

  it('image src points directly at publicWorkReportMediaUrl output, no blob:/data: prefix', () => {
    mockQuery.data = { pages: [makePage([makeReport({ id: 42, before: [1], after: [2] })])] }
    render(<WorkReportsModule />)

    const images = screen.getAllByRole('img')
    const srcs = images.map(img => img.getAttribute('src'))
    expect(srcs).toEqual([publicWorkReportMediaUrl(42, 1), publicWorkReportMediaUrl(42, 2)])
    for (const src of srcs) {
      expect(src).not.toMatch(/^blob:/)
      expect(src).not.toMatch(/^data:/)
    }
  })

  it('both before and after images carry loading="lazy"', () => {
    mockQuery.data = { pages: [makePage([makeReport()])] }
    render(<WorkReportsModule />)

    for (const img of screen.getAllByRole('img')) {
      expect(img).toHaveAttribute('loading', 'lazy')
    }
  })

  it('onError swaps a broken image to the placeholder', () => {
    mockQuery.data = { pages: [makePage([makeReport()])] }
    render(<WorkReportsModule />)

    const images = screen.getAllByRole('img')
    expect(images).toHaveLength(2)
    const beforeImg = images[0]
    fireEvent.error(beforeImg)

    // Плейсхолдер рендерит alt-текст ("До") вместо битого <img>. Таких узлов
    // теперь ДВА: подпись под парой миниатюр и сам плейсхолдер — поэтому
    // getAllByText, а не getByText. Существенное здесь — что <img> стало на
    // один меньше.
    expect(screen.getAllByText('До')).toHaveLength(2)
    expect(screen.getAllByRole('img')).toHaveLength(1)
  })

  it('caps rendered cards at MAX_CARDS (6) even when more items are returned', () => {
    const reports = Array.from({ length: 9 }, (_, i) =>
      makeReport({ id: i + 1, address: `Адрес ${i + 1}` }),
    )
    mockQuery.data = { pages: [makePage(reports)] }
    render(<WorkReportsModule />)

    expect(screen.getAllByRole('img')).toHaveLength(12) // 6 cards × 2 photos
    for (let i = 1; i <= 6; i++) {
      expect(screen.getByText(`Адрес ${i}`)).toBeInTheDocument()
    }
    for (let i = 7; i <= 9; i++) {
      expect(screen.queryByText(`Адрес ${i}`)).not.toBeInTheDocument()
    }
  })

  it('"view all" link points to /work-reports', () => {
    mockQuery.data = { pages: [makePage([makeReport()])] }
    render(<WorkReportsModule />)

    expect(screen.getByRole('link', { name: 'Все отчёты' })).toHaveAttribute('href', '/work-reports')
  })

  // Настройки из board_config (`work_reports.limit` / `.title`) редактируются
  // менеджером на странице модерации. До этих тестов они были write-only:
  // сохранялись и не влияли ни на что.
  it('honours the manager-configured limit instead of the hardcoded default', () => {
    const reports = Array.from({ length: 9 }, (_, i) =>
      makeReport({ id: i + 1, address: `Адрес ${i + 1}` }),
    )
    mockQuery.data = { pages: [makePage(reports)] }
    render(<WorkReportsModule limit={2} />)

    expect(screen.getByText('Адрес 1')).toBeInTheDocument()
    expect(screen.getByText('Адрес 2')).toBeInTheDocument()
    expect(screen.queryByText('Адрес 3')).not.toBeInTheDocument()
  })

  it('falls back to the default limit when the config has not loaded yet', () => {
    const reports = Array.from({ length: 9 }, (_, i) =>
      makeReport({ id: i + 1, address: `Адрес ${i + 1}` }),
    )
    mockQuery.data = { pages: [makePage(reports)] }
    render(<WorkReportsModule limit={undefined} />)

    expect(screen.getByText('Адрес 6')).toBeInTheDocument()
    expect(screen.queryByText('Адрес 7')).not.toBeInTheDocument()
  })

  it('renders the manager-configured title, falling back to i18n when empty', () => {
    mockQuery.data = { pages: [makePage([makeReport()])] }
    const { unmount } = render(<WorkReportsModule title="Наши работы" />)
    expect(screen.getByText('Наши работы')).toBeInTheDocument()
    unmount()

    render(<WorkReportsModule title="" />)
    expect(screen.getByText('Отчёты о работах')).toBeInTheDocument()  // board.sections.workReports
  })

  it('each thumbnail links to its own report page', () => {
    const reports = [makeReport({ id: 7 }), makeReport({ id: 9, address: 'Двор Б' })]
    mockQuery.data = { pages: [makePage(reports)] }
    render(<WorkReportsModule />)

    // Ссылка — вся плитка, а не мелкая зона: табло висит на телевизоре/тач-панели.
    expect(screen.getByRole('link', { name: /Двор Б/ })).toHaveAttribute(
      'href',
      '/work-reports/9',
    )
    const hrefs = screen
      .getAllByRole('link')
      .map((a) => a.getAttribute('href'))
    expect(hrefs).toContain('/work-reports/7')
    expect(hrefs).toContain('/work-reports/9')
  })

  it('labels each thumbnail half with До/После', () => {
    mockQuery.data = { pages: [makePage([makeReport()])] }
    render(<WorkReportsModule />)

    // Пара без подписей читается неоднозначно, особенно когда кадры похожи —
    // на странице архива подписи были, на табло их не было.
    expect(screen.getByText('До')).toBeInTheDocument()
    expect(screen.getByText('После')).toBeInTheDocument()
  })
})
