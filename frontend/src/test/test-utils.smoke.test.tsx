import { describe, expect, it } from 'vitest'
import { render, screen } from './test-utils'

// Validates the Phase-0 provider stack (QueryClient + i18n + Router) mounts.
describe('test-utils harness', () => {
  it('renders children inside all providers', () => {
    render(<div>hello-harness</div>)
    expect(screen.getByText('hello-harness')).toBeInTheDocument()
  })
})
