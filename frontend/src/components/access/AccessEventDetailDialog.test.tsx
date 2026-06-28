import { describe, it, expect } from 'vitest'
import { http, HttpResponse } from 'msw'
import { screen, waitFor } from '@testing-library/react'
import { render } from '@/test/test-utils'
import { server } from '@/test/msw/server'
import AccessEventDetailDialog from './AccessEventDetailDialog'

// Деталь события: тянет /events/:id через MSW и показывает крупные фото
// проезда (обзор авто + номер) рядом с контекстом камеры.

const detail = {
  camera_event: {
    id: 1,
    event_id: 'E-1',
    controller_id: 1,
    zone_id: 1,
    gate_id: 1,
    camera_id: 4,
    direction: 'entry',
    plate_number_original: '01A 777 BC',
    plate_number_normalized: '01A777BC',
    confidence: 0.91,
    captured_at: new Date().toISOString(),
    received_at: new Date().toISOString(),
    source: 'anpr',
    overview_photo_url: 'data:image/svg+xml,<svg/>overview',
    plate_photo_url: 'data:image/svg+xml,<svg/>plate',
    vehicle_class: 'легковой',
    color: 'белый',
  },
  decisions: [],
  barrier_commands: [],
  manual_openings: [],
  resident_confirmations: [],
}

describe('AccessEventDetailDialog', () => {
  it('показывает фото авто и номера в детали', async () => {
    server.use(
      http.get('*/api/v1/access/events/1', () => HttpResponse.json(detail)),
    )
    render(<AccessEventDetailDialog eventId={1} onClose={() => {}} />)
    await waitFor(() =>
      expect(screen.getByRole('img', { name: 'Фото автомобиля' })).toBeInTheDocument(),
    )
    expect(screen.getByRole('img', { name: 'Фото номера' })).toHaveAttribute(
      'src',
      'data:image/svg+xml,<svg/>plate',
    )
  })

  it('показывает ответ жителя (подтвердил/отклонил) при непустом resident_confirmations', async () => {
    const withConfirmations = {
      ...detail,
      resident_confirmations: [
        { user_id: 42, response: 'confirm', created_at: new Date().toISOString() },
        { user_id: 77, response: 'deny', created_at: new Date().toISOString() },
      ],
    }
    server.use(
      http.get('*/api/v1/access/events/2', () => HttpResponse.json(withConfirmations)),
    )
    render(<AccessEventDetailDialog eventId={2} onClose={() => {}} />)
    await waitFor(() =>
      expect(screen.getByText('Ответ жителя')).toBeInTheDocument(),
    )
    expect(screen.getByText('Подтвердил')).toBeInTheDocument()
    expect(screen.getByText('Отклонил')).toBeInTheDocument()
    expect(screen.getByText('Совещательно — решение принимает оператор')).toBeInTheDocument()
  })

  it('не показывает секцию ответа жителя при пустом resident_confirmations', async () => {
    server.use(
      http.get('*/api/v1/access/events/1', () => HttpResponse.json(detail)),
    )
    render(<AccessEventDetailDialog eventId={1} onClose={() => {}} />)
    await waitFor(() =>
      expect(screen.getByRole('img', { name: 'Фото автомобиля' })).toBeInTheDocument(),
    )
    expect(screen.queryByText('Ответ жителя')).not.toBeInTheDocument()
  })
})
