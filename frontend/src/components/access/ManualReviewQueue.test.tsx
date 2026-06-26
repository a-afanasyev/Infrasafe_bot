import { describe, it, expect } from 'vitest'
import { http, HttpResponse } from 'msw'
import { screen, waitFor, fireEvent } from '@testing-library/react'
import { render } from '@/test/test-utils'
import { server } from '@/test/msw/server'
import ManualReviewQueue from './ManualReviewQueue'

// Очередь ручной проверки: тянет события decision=manual_review через MSW,
// показывает действия и открывает диалог резолюции.

const pendingEvent = {
  id: 1,
  event_id: 'E-1',
  controller_id: 1,
  zone_id: 7,
  gate_id: 3,
  direction: 'entry',
  plate_number_normalized: '01A777BC',
  captured_at: new Date().toISOString(),
  occurred_at: new Date().toISOString(),
  source: 'anpr',
  decision: 'manual_review',
  status: 'pending_review',
  reason: 'manual_review_required',
  decision_id: 5,
  resolved_by_user_id: null,
  has_command: false,
}

describe('ManualReviewQueue', () => {
  it('рендерит событие очереди и кнопки действий', async () => {
    server.use(
      http.get('*/api/v1/access/events', () =>
        HttpResponse.json({ items: [pendingEvent], total: 1, limit: 50, offset: 0 }),
      ),
    )
    render(<ManualReviewQueue />)
    await waitFor(() => expect(screen.getByText('01A777BC')).toBeInTheDocument())
    expect(screen.getByText('Открыть с причиной')).toBeInTheDocument()
    expect(screen.getByText('Отказать')).toBeInTheDocument()
  })

  it('кнопка «Открыть с причиной» открывает диалог с полями шлагбаума и причины', async () => {
    server.use(
      http.get('*/api/v1/access/events', () =>
        HttpResponse.json({ items: [pendingEvent], total: 1, limit: 50, offset: 0 }),
      ),
    )
    render(<ManualReviewQueue />)
    await waitFor(() => expect(screen.getByText('01A777BC')).toBeInTheDocument())
    fireEvent.click(screen.getByText('Открыть с причиной'))
    // Диалог: barrier_id предзаполнен gate_id (3) + поле причины.
    expect(screen.getByText('Открыть шлагбаум')).toBeInTheDocument()
    expect(screen.getByLabelText('ID шлагбаума')).toHaveValue(3)
    expect(screen.getByLabelText('Причина')).toBeInTheDocument()
  })

  it('пустая очередь → пустое состояние', async () => {
    server.use(
      http.get('*/api/v1/access/events', () =>
        HttpResponse.json({ items: [], total: 0, limit: 50, offset: 0 }),
      ),
    )
    render(<ManualReviewQueue />)
    await waitFor(() => expect(screen.getByText('Нет событий на проверке')).toBeInTheDocument())
  })
})
