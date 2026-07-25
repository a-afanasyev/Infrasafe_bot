import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen } from '../test/test-utils'
import WorkReportDetailPage from './WorkReportDetailPage'
import {
  publicWorkReportMediaUrl,
  publicWorkReportOriginalUrl,
} from '../hooks/usePublicWorkReports'
import type { PublicWorkReport } from '../types/workReports'

// Страница одного отчёта — цель нажатия по миниатюре на табло. Хук мокаем тем
// же приёмом, что WorkReportsModule.test.tsx / WorkReportsArchivePage.test.tsx
// (vi.hoisted + vi.mock), чтобы прогонять состояния загрузки/404 без MSW.
const { mockQuery, mockParams } = vi.hoisted(() => ({
  mockQuery: {
    data: undefined as PublicWorkReport | undefined,
    isLoading: false,
    isError: false,
  },
  mockParams: { reportId: '42' as string | undefined },
}))

// `test-utils.render` уже оборачивает дерево в MemoryRouter без initialEntries,
// поэтому URL там всегда "/" и route-параметр так не задать. Подменяем ТОЛЬКО
// useParams, а не весь react-router: Link/роутер остаются настоящими, иначе
// тест на href'ы проверял бы заглушку.
vi.mock('react-router', async () => {
  const actual = await vi.importActual<typeof import('react-router')>('react-router')
  return { ...actual, useParams: () => ({ reportId: mockParams.reportId }) }
})

vi.mock('../hooks/usePublicWorkReports', async () => {
  const actual = await vi.importActual<typeof import('../hooks/usePublicWorkReports')>(
    '../hooks/usePublicWorkReports',
  )
  return {
    ...actual,
    usePublicWorkReport: () => mockQuery,
  }
})

function makeReport(over: Partial<PublicWorkReport> = {}): PublicWorkReport {
  return {
    id: 42,
    category_key: 'plumbing',
    address: 'ул. Амира Темура, 14 (Двор Olmazor)',
    completed_on: '2026-07-20',
    before: [101, 102],
    after: [201],
    ...over,
  }
}

function renderAt(reportId: string) {
  mockParams.reportId = reportId
  return render(<WorkReportDetailPage />)
}

beforeEach(() => {
  mockQuery.data = undefined
  mockQuery.isLoading = false
  mockQuery.isError = false
  mockParams.reportId = '42'
})

describe('WorkReportDetailPage', () => {
  it('renders category, address, date and ALL photos of both sides', () => {
    mockQuery.data = makeReport()
    renderAt('42')

    expect(screen.getByText('Сантехника')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /Амира Темура/ })).toBeInTheDocument()

    // Отличие от миниатюры: показываются ВСЕ кадры, а не первая пара.
    const images = screen.getAllByRole('img')
    expect(images).toHaveLength(3)
    expect(images.map((i) => i.getAttribute('src'))).toEqual([
      publicWorkReportMediaUrl(42, 101),
      publicWorkReportMediaUrl(42, 102),
      publicWorkReportMediaUrl(42, 201),
    ])
  })

  it('shows a "not found" state on error rather than a server-error message', () => {
    // 404 приходит и на снятый с публикации отчёт — это ожидаемый ответ.
    mockQuery.isError = true
    renderAt('42')

    expect(screen.getByText('Отчёт не найден или снят с публикации')).toBeInTheDocument()
    expect(screen.queryAllByRole('img')).toHaveLength(0)
  })

  it('renders a placeholder instead of an empty column when a side has no photos', () => {
    mockQuery.data = makeReport({ after: [] })
    renderAt('42')

    // Пустая сторона у опубликованного отчёта — состояние, которого быть не
    // должно (publish требует обе), но «ничего» читалось бы как поломка вёрстки.
    expect(screen.getAllByRole('img')).toHaveLength(2)
    expect(screen.getAllByText('После').length).toBeGreaterThan(0)
  })

it('фото ведёт на оригинал, а показывает превью', () => {
    // Превью лежат в дисковом кэше media-service; оригинал — скачивание из
    // Telegram, поэтому он только по адресному клику (инцидент 2026-07-25:
    // 60 оригиналов на одну загрузку витрины выели пул соединений).
    mockQuery.data = makeReport({ before: [101], after: [201] })
    renderAt('42')

    const images = screen.getAllByRole('img')
    expect(images[0].getAttribute('src')).toBe(publicWorkReportMediaUrl(42, 101))
    expect(images[0].getAttribute('src')).not.toContain('original')

    const hrefs = screen.getAllByRole('link').map((a) => a.getAttribute('href'))
    expect(hrefs).toContain(publicWorkReportOriginalUrl(42, 101))
    expect(hrefs).toContain(publicWorkReportOriginalUrl(42, 201))
  })

  it('links back to the board and to the full archive', () => {
    mockQuery.data = makeReport()
    renderAt('42')

    const hrefs = screen.getAllByRole('link').map((a) => a.getAttribute('href'))
    expect(hrefs).toContain('/resident-board')
    expect(hrefs).toContain('/work-reports')
  })
})
