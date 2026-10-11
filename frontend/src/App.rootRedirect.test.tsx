import { describe, it, expect, afterEach } from 'vitest'
import { Route, Routes } from 'react-router'
import { render, screen } from './test/test-utils'
import { useAuthStore } from './stores/authStore'
import { RootRedirect } from './App'

// «/» для гостя ведёт на страницу жителей (/home), а не на табло для экрана;
// вошедший сотрудник — в дашборд.

function renderRoot() {
  render(
    <Routes>
      <Route path="/" element={<RootRedirect />} />
      <Route path="/home" element={<div>HOME</div>} />
      <Route path="/resident-board" element={<div>BOARD</div>} />
      <Route path="/dashboard" element={<div>DASHBOARD</div>} />
    </Routes>,
    { routerEntries: ['/'] },
  )
}

afterEach(() => {
  useAuthStore.setState({ user: null, isAuthenticated: false, hydrating: true })
})

describe('RootRedirect', () => {
  it('гость → страница жителей', () => {
    useAuthStore.setState({ user: null, isAuthenticated: false, hydrating: false })
    renderRoot()
    expect(screen.getByText('HOME')).toBeInTheDocument()
  })

  it('сотрудник → дашборд', () => {
    useAuthStore.setState({ user: { id: 1, roles: ['manager'] }, isAuthenticated: true, hydrating: false })
    renderRoot()
    expect(screen.getByText('DASHBOARD')).toBeInTheDocument()
  })
})
