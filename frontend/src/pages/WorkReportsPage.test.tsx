import { describe, it, expect } from 'vitest'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { render, screen, waitFor, within } from '../test/test-utils'
import { server } from '../test/msw/server'
import WorkReportsPage from './WorkReportsPage'
import type { WorkReport } from '../types/workReports'
import type { WorkReportsCfg } from '../types/boardConfig'

const DEFAULT_CFG: WorkReportsCfg = {
  autopost: false,
  autopost_since: null,
  limit: 6,
  title: { ru: '', uz: '' },
}

function makeReport(overrides: Partial<WorkReport> & { id: number; status: WorkReport['status'] }): WorkReport {
  return {
    request_number: `26072${overrides.id}-001`,
    category_key: 'electricity',
    address_public: 'ул. Примерная, 1',
    performed_at: '2026-07-20T10:00:00',
    before_media_ids: [],
    after_media_ids: [],
    media_meta: [],
    locked_media_ids: [],
    source: 'auto',
    reject_reason: null,
    created_at: '2026-07-20T10:00:00',
    published_at: null,
    media_synced_at: null,
    state_changed_at: null,
    moderated_by: null,
    ...overrides,
  }
}

function mockBoardConfig(work_reports: WorkReportsCfg = DEFAULT_CFG) {
  return http.get('*/api/v2/public/board-config', () => HttpResponse.json({ work_reports }))
}

function mockList(items: WorkReport[]) {
  return http.get('*/api/v2/work-reports', () =>
    HttpResponse.json({ items, total: items.length, limit: 50, offset: 0 }),
  )
}

describe('WorkReportsPage', () => {
  it('shows the privacy warning unconditionally', async () => {
    server.use(mockBoardConfig(), mockList([]))
    render(<WorkReportsPage />)
    expect(
      await screen.findByText(/Анонимизация адреса не анонимизирует само фото/),
    ).toBeInTheDocument()
  })

  it('fires PUT .../settings with the new autopost value and reflects server state', async () => {
    let autopost = false
    server.use(
      http.get('*/api/v2/public/board-config', () =>
        HttpResponse.json({ work_reports: { ...DEFAULT_CFG, autopost } }),
      ),
      mockList([]),
      http.put('*/api/v2/work-reports/settings', async ({ request }) => {
        const body = (await request.json()) as Record<string, unknown>
        expect(body).toEqual({ autopost: true })
        autopost = true
        return HttpResponse.json({ ...DEFAULT_CFG, autopost })
      }),
    )
    const user = userEvent.setup()
    render(<WorkReportsPage />)

    const checkbox = await screen.findByRole('checkbox', { name: 'Автопубликация' })
    expect(checkbox).not.toBeChecked()
    await user.click(checkbox)
    await waitFor(() => expect(checkbox).toBeChecked())
  })

  it('creates a draft via POST /api/v2/work-reports with the entered request_number', async () => {
    let created: Record<string, unknown> | null = null
    server.use(
      mockBoardConfig(),
      mockList([]),
      http.post('*/api/v2/work-reports', async ({ request }) => {
        created = (await request.json()) as Record<string, unknown>
        return HttpResponse.json(makeReport({ id: 99, status: 'pending', request_number: '260725-005' }))
      }),
    )
    const user = userEvent.setup()
    render(<WorkReportsPage />)

    const input = await screen.findByPlaceholderText('Например, 260725-001')
    await user.type(input, '260725-005')
    await user.click(screen.getByRole('button', { name: 'Создать' }))

    await waitFor(() => expect(created).toEqual({ request_number: '260725-005' }))
  })

  it('disables Publish and shows the explanation for a needs_media report', async () => {
    const report = makeReport({ id: 1, status: 'needs_media' })
    server.use(mockBoardConfig(), mockList([report]))
    render(<WorkReportsPage />)

    const publishBtn = await screen.findByRole('button', { name: 'Опубликовать' })
    expect(publishBtn).toBeDisabled()
    expect(screen.getByText('Нужны фото «до» и «после», чтобы опубликовать')).toBeInTheDocument()
  })

  it('shows a needs_review report in its own group with the reject_reason', async () => {
    const report = makeReport({
      id: 3,
      status: 'needs_review',
      reject_reason: 'Виден номер автомобиля',
    })
    server.use(mockBoardConfig(), mockList([report]))
    render(<WorkReportsPage />)

    expect(await screen.findByText('Требует внимания')).toBeInTheDocument()
    expect(screen.getByText('Виден номер автомобиля')).toBeInTheDocument()
  })

  it('reject sends POST .../reject with the typed reason and re-fetches the list', async () => {
    const report = makeReport({ id: 2, status: 'pending' })
    let getListCalls = 0
    let rejectBody: Record<string, unknown> | null = null
    server.use(
      mockBoardConfig(),
      http.get('*/api/v2/work-reports', () => {
        getListCalls++
        return HttpResponse.json({ items: [report], total: 1, limit: 50, offset: 0 })
      }),
      http.post('*/api/v2/work-reports/2/reject', async ({ request }) => {
        rejectBody = (await request.json()) as Record<string, unknown>
        return HttpResponse.json({ ...report, status: 'rejected' })
      }),
    )
    const user = userEvent.setup()
    render(<WorkReportsPage />)

    await screen.findByText(report.address_public, { exact: false })
    const callsBefore = getListCalls

    await user.click(screen.getByRole('button', { name: 'Отклонить' }))
    const dialog = await screen.findByRole('dialog')
    await user.type(within(dialog).getByPlaceholderText('Причина'), 'Плохое фото')
    await user.click(within(dialog).getByRole('button', { name: 'Отклонить' }))

    await waitFor(() => expect(rejectBody).toEqual({ reason: 'Плохое фото' }))
    await waitFor(() => expect(getListCalls).toBeGreaterThan(callsBefore))
  })

  it('unpublish sends POST .../unpublish (reason optional) and re-fetches the list', async () => {
    const report = makeReport({ id: 4, status: 'published' })
    let getListCalls = 0
    let unpublishBody: Record<string, unknown> | null = null
    server.use(
      mockBoardConfig(),
      http.get('*/api/v2/work-reports', () => {
        getListCalls++
        return HttpResponse.json({ items: [report], total: 1, limit: 50, offset: 0 })
      }),
      http.post('*/api/v2/work-reports/4/unpublish', async ({ request }) => {
        unpublishBody = (await request.json()) as Record<string, unknown>
        return HttpResponse.json({ ...report, status: 'rejected' })
      }),
    )
    const user = userEvent.setup()
    render(<WorkReportsPage />)

    await screen.findByText(report.address_public, { exact: false })
    const callsBefore = getListCalls

    await user.click(screen.getByRole('button', { name: 'Снять с публикации' }))
    const dialog = await screen.findByRole('dialog')
    // Причина необязательна для unpublish — подтверждаем без ввода текста.
    await user.click(within(dialog).getByRole('button', { name: 'Снять с публикации' }))

    await waitFor(() => expect(unpublishBody).toEqual({ reason: '' }))
    await waitFor(() => expect(getListCalls).toBeGreaterThan(callsBefore))
  })

  it('reopen sends POST .../reopen and re-fetches the list', async () => {
    const report = makeReport({ id: 5, status: 'rejected' })
    let getListCalls = 0
    let reopenCalled = false
    server.use(
      mockBoardConfig(),
      http.get('*/api/v2/work-reports', () => {
        getListCalls++
        return HttpResponse.json({ items: [report], total: 1, limit: 50, offset: 0 })
      }),
      http.post('*/api/v2/work-reports/5/reopen', () => {
        reopenCalled = true
        return HttpResponse.json({ ...report, status: 'pending' })
      }),
    )
    const user = userEvent.setup()
    render(<WorkReportsPage />)

    await screen.findByText(report.address_public, { exact: false })
    const callsBefore = getListCalls

    await user.click(screen.getByRole('button', { name: 'Вернуть в работу' }))
    const dialog = await screen.findByRole('alertdialog')
    await user.click(within(dialog).getByRole('button', { name: 'Вернуть в работу' }))

    await waitFor(() => expect(reopenCalled).toBe(true))
    await waitFor(() => expect(getListCalls).toBeGreaterThan(callsBefore))
  })
})
