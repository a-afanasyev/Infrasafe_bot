import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router'
import { http, HttpResponse } from 'msw'
import { server } from '../test/msw/server'
import TWAApp from './App'

// Кнопка «Открыть» в наряде исполнителю (бот) ведёт прямо на
// /uk/twa/exec/tasks/<номер>. Глубокий путь обязан открыть карточку, а не
// увести на RoleLanding/главную — в том числе когда активная роль не executor
// (RoleGuard смотрит на roles целиком).

vi.mock('./hooks/useTWAAuth', () => ({
  useTWAAuth: () => ({ accessToken: 't', isLoading: false, isAuthenticated: true }),
}))
vi.mock('./hooks/useTelegramSDK', () => ({
  useTelegramSDK: () => ({ colorScheme: 'light', initData: '', haptic: () => {}, close: () => {} }),
}))
vi.mock('./pages/executor/TaskDetailPage', () => ({
  default: () => <div>task-detail-stub</div>,
}))

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/twa/*" element={<TWAApp />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('TWA deep-link to executor task card', () => {
  it.each([
    ['executor', ['executor']],
    ['applicant', ['applicant', 'executor']],
  ])('opens the card when active_role=%s', async (activeRole, roles) => {
    server.use(
      http.get('*/api/v2/profile', () =>
        HttpResponse.json({ id: 1, telegram_id: 42, language: 'ru', roles, active_role: activeRole }),
      ),
    )
    renderAt('/twa/exec/tasks/260925-001')
    expect(await screen.findByText('task-detail-stub')).toBeInTheDocument()
  })
})
