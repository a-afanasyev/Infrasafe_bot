import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import RootToaster from './RootToaster'

function mountAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <RootToaster />
    </MemoryRouter>,
  )
}

describe('RootToaster', () => {
  it('на дашборде монтирует тостер', () => {
    const { container } = mountAt('/dashboard')
    expect(container.querySelector('section[aria-label]')).not.toBeNull()
  })

  it('в TWA не монтирует второй тостер (у Mini App свой)', () => {
    const { container } = mountAt('/twa/exec/tasks')
    expect(container.querySelector('section[aria-label]')).toBeNull()
  })
})
