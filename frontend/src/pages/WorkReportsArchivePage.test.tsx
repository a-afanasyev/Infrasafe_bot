import { describe, it, expect, beforeEach, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
import { render, screen } from '../test/test-utils'
import WorkReportsArchivePage from './WorkReportsArchivePage'
import { publicWorkReportMediaUrl } from '../hooks/usePublicWorkReports'
import type { PublicWorkReport, PublicWorkReportsPage } from '../types/workReports'

// T12 — WorkReportsArchivePage reads data via usePublicWorkReports() (no
// props), mocked the same way WorkReportsModule.test.tsx mocks the hook:
// vi.hoisted shared object + vi.mock returning it, so each test can drive
// data/isLoading/hasNextPage/isFetchingNextPage/fetchNextPage directly
// without standing up MSW handlers for infinite-scroll pagination.
const { mockQuery, fetchNextPage } = vi.hoisted(() => ({
  mockQuery: {
    data: undefined as { pages: PublicWorkReportsPage[] } | undefined,
    isLoading: false,
    hasNextPage: false,
    isFetchingNextPage: false,
  },
  fetchNextPage: vi.fn(),
}))

vi.mock('../hooks/usePublicWorkReports', async () => {
  const actual = await vi.importActual<typeof import('../hooks/usePublicWorkReports')>(
    '../hooks/usePublicWorkReports',
  )
  return {
    ...actual,
    usePublicWorkReports: () => ({ ...mockQuery, fetchNextPage }),
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

function makePage(items: PublicWorkReport[], total = items.length): PublicWorkReportsPage {
  return { items, total, limit: 12, offset: 0 }
}

beforeEach(() => {
  mockQuery.data = undefined
  mockQuery.isLoading = false
  mockQuery.hasNextPage = false
  mockQuery.isFetchingNextPage = false
  fetchNextPage.mockClear()
})

describe('WorkReportsArchivePage', () => {
  it('shows the loading spinner before the first page arrives', () => {
    mockQuery.isLoading = true
    mockQuery.data = undefined
    const { container } = render(<WorkReportsArchivePage />)
    expect(container.querySelector('.animate-spin')).toBeInTheDocument()
  })

  it('shows the empty state when loaded with zero published reports', async () => {
    mockQuery.data = { pages: [makePage([])] }
    render(<WorkReportsArchivePage />)
    expect(await screen.findByText('Пока нет опубликованных отчётов')).toBeInTheDocument()
  })

  it('renders report cards from the first page', async () => {
    mockQuery.data = { pages: [makePage([makeReport(), makeReport({ id: 2, address: 'Дом 2, кв 9' })])] }
    render(<WorkReportsArchivePage />)

    expect(await screen.findByText('Дом 1, кв 5')).toBeInTheDocument()
    expect(screen.getByText('Дом 2, кв 9')).toBeInTheDocument()
    expect(screen.getAllByText('Электрика')).toHaveLength(2)
    expect(screen.getAllByRole('img')).toHaveLength(4)
  })

  it('has a link back to the resident board', async () => {
    mockQuery.data = { pages: [makePage([makeReport()])] }
    render(<WorkReportsArchivePage />)
    expect(await screen.findByRole('link', { name: '← На табло' })).toHaveAttribute('href', '/resident-board')
  })

  it('photo src points directly at publicWorkReportMediaUrl output, no blob:/data: prefix', async () => {
    mockQuery.data = { pages: [makePage([makeReport({ id: 42, before: [1], after: [2] })])] }
    render(<WorkReportsArchivePage />)

    const images = await screen.findAllByRole('img')
    const srcs = images.map(img => img.getAttribute('src'))
    expect(srcs).toEqual([publicWorkReportMediaUrl(42, 1), publicWorkReportMediaUrl(42, 2)])
    for (const src of srcs) {
      expect(src).not.toMatch(/^blob:/)
      expect(src).not.toMatch(/^data:/)
    }
  })

  it('formats "2026-01-01" as "01.01.2026", not shifted a day by UTC parsing', async () => {
    mockQuery.data = { pages: [makePage([makeReport({ completed_on: '2026-01-01' })])] }
    render(<WorkReportsArchivePage />)

    expect(await screen.findByText('01.01.2026')).toBeInTheDocument()
    expect(screen.queryByText('31.12.2025')).not.toBeInTheDocument()
  })

  it('shows the "load more" button when hasNextPage is true and calls fetchNextPage on click', async () => {
    mockQuery.data = { pages: [makePage([makeReport()], 20)] }
    mockQuery.hasNextPage = true
    const user = userEvent.setup()
    render(<WorkReportsArchivePage />)

    const btn = await screen.findByRole('button', { name: 'Показать ещё' })
    await user.click(btn)
    expect(fetchNextPage).toHaveBeenCalledTimes(1)
  })

  it('shows the loading label while isFetchingNextPage is true', async () => {
    mockQuery.data = { pages: [makePage([makeReport()], 20)] }
    mockQuery.hasNextPage = true
    mockQuery.isFetchingNextPage = true
    render(<WorkReportsArchivePage />)

    expect(await screen.findByRole('button', { name: 'Загрузка…' })).toBeDisabled()
  })

  it('hides the "load more" button once hasNextPage is false', async () => {
    mockQuery.data = { pages: [makePage([makeReport()])] }
    mockQuery.hasNextPage = false
    render(<WorkReportsArchivePage />)

    await screen.findByText('Дом 1, кв 5')
    expect(screen.queryByRole('button', { name: 'Показать ещё' })).not.toBeInTheDocument()
  })

  it('page-gluing: newly loaded items from a second page appear alongside the first', async () => {
    mockQuery.data = {
      pages: [
        makePage([makeReport({ id: 1, address: 'Дом 1, кв 5' })], 2),
        makePage([makeReport({ id: 2, address: 'Дом 2, кв 9' })], 2),
      ],
    }
    render(<WorkReportsArchivePage />)

    expect(await screen.findByText('Дом 1, кв 5')).toBeInTheDocument()
    expect(screen.getByText('Дом 2, кв 9')).toBeInTheDocument()
  })
})
