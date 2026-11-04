import { describe, it, expect } from 'vitest'
import { render, screen } from '../../test/test-utils'
import { ResidentAccountBadge, ResidentVerificationBadge } from './ResidentStatusBadge'

describe('ResidentVerificationBadge', () => {
  it('запрошены, но не загружены — «Запрошены документы»', () => {
    render(<ResidentVerificationBadge status="requested" />)
    expect(screen.getByText('Запрошены документы')).toBeInTheDocument()
  })

  it('запрошены и загружены — «Документы предоставлены»', () => {
    render(<ResidentVerificationBadge status="requested" submitted />)
    expect(screen.getByText('Документы предоставлены')).toBeInTheDocument()
  })

  it('признак не перекрывает итоговый статус', () => {
    render(<ResidentVerificationBadge status="verified" submitted />)
    expect(screen.getByText('Подтверждён')).toBeInTheDocument()
  })
})

describe('ResidentAccountBadge — незавершённая регистрация', () => {
  it.each([
    ['pending', null, 0, 'Не завершил регистрацию'],
    ['pending', '+998901234567', 0, 'Ожидает'],
    ['pending', null, 1, 'Ожидает'],
    ['approved', null, 0, 'Одобрен'],
  ] as const)('%s, телефон %s, квартир %s → «%s»', (status, phone, apartmentsCount, label) => {
    render(<ResidentAccountBadge status={status} phone={phone} apartmentsCount={apartmentsCount} />)
    expect(screen.getByText(label)).toBeInTheDocument()
  })

  it('без данных о телефоне и квартирах — обычный статус', () => {
    render(<ResidentAccountBadge status="pending" />)
    expect(screen.getByText('Ожидает')).toBeInTheDocument()
  })
})
