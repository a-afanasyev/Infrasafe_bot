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

    // Placeholder renders the alt text ("До") instead of the broken <img>.
    expect(screen.getByText('До')).toBeInTheDocument()
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
})
