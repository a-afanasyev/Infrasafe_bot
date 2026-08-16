import { describe, it, expect } from 'vitest'
import { screen } from '@testing-library/react'
import { render } from '../../test/test-utils'
import RequestCard from './RequestCard'
import type { RequestCard as TCard } from '../../hooks/useKanban'

// Первый тест-файл на RequestCard: до появления индикаторов карточка была
// чисто презентационной и покрывалась косвенно через доску.

const CARD: TCard = {
  request_number: '260816-001',
  status: 'Уточнение',
  category: 'elevator',
  urgency: 'medium',
  source: 'bot',
  description: 'Не работает лифт',
  address: 'Дом 1',
  executor_id: null,
  executor_name: null,
  notes: null,
  completion_report: null,
  requested_materials: null,
  return_reason: null,
  created_at: '2026-08-16T09:00:00Z',
  updated_at: '2026-08-16T10:00:00Z',
  manager_confirmed: false,
}

describe('RequestCard — индикатор непрочитанного', () => {
  it('без пропа unread точки нет', () => {
    render(<RequestCard card={CARD} onClick={() => {}} />)

    expect(screen.queryByTestId('unread-dot')).not.toBeInTheDocument()
  })

  it('с unread показывает точку', () => {
    render(<RequestCard card={CARD} onClick={() => {}} unread />)

    expect(screen.getByTestId('unread-dot')).toBeInTheDocument()
  })

  it('для «Уточнения» добавляет бейдж «новый ответ»', () => {
    render(<RequestCard card={CARD} onClick={() => {}} unread />)

    expect(screen.getByText(/новый ответ/i)).toBeInTheDocument()
  })

  it('для «Закупа» бейджа про ответ нет — только точка', () => {
    render(<RequestCard card={{ ...CARD, status: 'Закуп' }} onClick={() => {}} unread />)

    expect(screen.getByTestId('unread-dot')).toBeInTheDocument()
    expect(screen.queryByText(/новый ответ/i)).not.toBeInTheDocument()
  })

  it('в «Закупе» без срочности контейнер бейджей не рендерится пустым', () => {
    // Иначе у карточки остался бы пустой div с mt-1: условие контейнера должно
    // смотреть на сам бейдж, а не на голый unread.
    const { container } = render(
      <RequestCard
        card={{ ...CARD, status: 'Закуп', urgency: null, manager_confirmed: false }}
        onClick={() => {}}
        unread
      />,
    )

    expect(container.querySelector('.flex.gap-1.flex-wrap')).toBeNull()
  })

  it('бейдж не проглатывается, когда у карточки нет ни срочности, ни подтверждения', () => {
    // Контейнер бейджей рендерился по условию (urgency || manager_confirmed);
    // без расширения условия бейдж «новый ответ» просто не появлялся бы.
    render(
      <RequestCard
        card={{ ...CARD, urgency: null, manager_confirmed: false }}
        onClick={() => {}}
        unread
      />,
    )

    expect(screen.getByText(/новый ответ/i)).toBeInTheDocument()
  })

  it('обычные данные карточки на месте (индикатор ничего не сломал)', () => {
    render(<RequestCard card={CARD} onClick={() => {}} unread />)

    expect(screen.getByText('260816-001')).toBeInTheDocument()
    expect(screen.getByText('Не работает лифт')).toBeInTheDocument()
  })
})
