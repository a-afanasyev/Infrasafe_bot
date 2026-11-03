import { describe, it, expect } from 'vitest'
import { render, screen } from '../../test/test-utils'
import { ResidentVerificationBadge } from './ResidentStatusBadge'

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
