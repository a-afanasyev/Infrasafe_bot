import { describe, it, expect } from 'vitest'
import { render, screen } from '@/test/test-utils'
import EmptyState from './EmptyState'
import LoadingSpinner from './LoadingSpinner'

// TEST-068 Phase 3: тривиальные presentational shared-компоненты.

describe('EmptyState', () => {
  it('renders icon, title and optional subtitle', () => {
    render(<EmptyState icon="📭" title="Пусто" subtitle="нет данных" />)
    expect(screen.getByText('📭')).toBeInTheDocument()
    expect(screen.getByText('Пусто')).toBeInTheDocument()
    expect(screen.getByText('нет данных')).toBeInTheDocument()
  })

  it('omits the subtitle when not provided', () => {
    render(<EmptyState icon="📭" title="Пусто" />)
    expect(screen.getByText('Пусто')).toBeInTheDocument()
    expect(screen.queryByText('нет данных')).not.toBeInTheDocument()
  })
})

describe('LoadingSpinner', () => {
  it('renders a spinning indicator', () => {
    const { container } = render(<LoadingSpinner />)
    expect(container.querySelector('.animate-spin')).not.toBeNull()
  })
})
