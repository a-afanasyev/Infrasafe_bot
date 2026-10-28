import { describe, it, expect, beforeEach } from 'vitest'
import { Routes, Route } from 'react-router'
import { render, screen } from './test/test-utils'
import { ProtectedRoute } from './App'
import { useAuthStore } from './stores/authStore'
import { actionsFor } from './test/authz'

// Защита маршрута «Правила ИИ»: действие auto_manager.configure. Без него —
// на /home, без входа — на /login с return-to.
function login(roles: string[] | null) {
  useAuthStore.setState({
    user: roles ? ({ id: 1, first_name: 'Мария', roles, actions: actionsFor(roles) } as never) : null,
    isAuthenticated: roles !== null,
    hydrating: false,
  } as never)
}

function renderAt(path: string) {
  return render(
    <Routes>
      <Route path="/dashboard/ai-manager" element={<ProtectedRoute action="auto_manager.configure"><div>ai page</div></ProtectedRoute>} />
      <Route path="/home" element={<div>home</div>} />
      <Route path="/login" element={<div>login</div>} />
    </Routes>,
    { routerEntries: [path] },
  )
}

beforeEach(() => login(null))

describe('ProtectedRoute — /dashboard/ai-manager', () => {
  it('manager sees the page', () => {
    login(['manager'])
    renderAt('/dashboard/ai-manager')
    expect(screen.getByText('ai page')).toBeInTheDocument()
  })

  it('executor without auto_manager.configure is sent to /home', () => {
    login(['executor'])
    renderAt('/dashboard/ai-manager')
    expect(screen.getByText('home')).toBeInTheDocument()
    expect(screen.queryByText('ai page')).not.toBeInTheDocument()
  })

  it('anonymous is sent to /login', () => {
    renderAt('/dashboard/ai-manager')
    expect(screen.getByText('login')).toBeInTheDocument()
  })
})
