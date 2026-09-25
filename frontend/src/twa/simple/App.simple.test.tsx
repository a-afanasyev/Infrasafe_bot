import { describe, it, expect, vi, beforeEach, afterAll } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Routes, Route, useLocation, useParams } from 'react-router'
import { http, HttpResponse } from 'msw'
import { server } from '../../test/msw/server'
import { markLangChosen, resetLangChosenForTests } from './langFlag'

// QueryClient TWA — модульный синглтон App.tsx: без свежего модуля профиль
// из предыдущего теста (staleTime 60 с) решал бы маршрут следующего.
let TWAApp: (typeof import('../App'))['default']

// Контракт маршрутов простого режима: бот ссылается только на
// /twa/exec/tasks/{n}[?action=done], куда вести — решает фронт по
// profile.simple_mode.

vi.mock('../hooks/useTWAAuth', () => ({
  useTWAAuth: () => ({ accessToken: 't', isLoading: false, isAuthenticated: true }),
}))
vi.mock('../hooks/useTelegramSDK', () => ({
  useTelegramSDK: () => ({
    colorScheme: 'light', initData: '', haptic: () => {}, notify: () => {}, close: () => {},
    showBackButton: () => () => {},
  }),
}))

function Stub({ name }: { name: string }) {
  const { number } = useParams()
  const { search } = useLocation()
  return <div>{`${name}${number ? ` ${number}` : ''}${search}`}</div>
}

vi.mock('../pages/executor/TaskDetailPage', () => ({ default: () => <Stub name="EXEC-DETAIL" /> }))
vi.mock('../pages/executor/CompletionReport', () => ({ default: () => <Stub name="EXEC-REPORT" /> }))
vi.mock('../pages/executor/TasksPage', () => ({ default: () => <Stub name="EXEC-TASKS" /> }))
vi.mock('../components/ExecutorTabs', () => ({ ExecutorTabs: () => null }))
vi.mock('./pages/MinePage', () => ({ default: () => <Stub name="SIMPLE-MINE" /> }))
vi.mock('./pages/TaskPage', () => ({ default: () => <Stub name="SIMPLE-TASK" /> }))
vi.mock('./pages/DonePage', () => ({ default: () => <Stub name="SIMPLE-DONE" /> }))
vi.mock('./pages/LangPage', () => ({ default: () => <Stub name="SIMPLE-LANG" /> }))

function mockProfile(simple: boolean) {
  server.use(
    http.get('*/api/v2/profile', () =>
      HttpResponse.json({
        id: 1, telegram_id: 42, language: 'ru', roles: ['executor'], active_role: 'executor', simple_mode: simple,
      }),
    ),
  )
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/twa/*" element={<TWAApp />} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(async () => {
  vi.resetModules()
  TWAApp = (await import('../App')).default
  markLangChosen()
})
afterAll(() => resetLangChosenForTests())

describe('simple mode routing', () => {
  it.each([
    ['/twa', 'SIMPLE-MINE'],
    ['/twa/exec', 'SIMPLE-MINE'],
    ['/twa/exec/tasks/260926-001', 'SIMPLE-TASK 260926-001'],
    ['/twa/exec/tasks/260926-001?action=done', 'SIMPLE-DONE 260926-001'],
  ])('simple_mode=true: %s → %s', async (path, expected) => {
    mockProfile(true)
    renderAt(path)
    expect(await screen.findByText(expected)).toBeInTheDocument()
  })

  it.each([
    ['/twa', 'EXEC-TASKS'],
    ['/twa/exec', 'EXEC-TASKS'],
    ['/twa/exec/tasks/260926-001', 'EXEC-DETAIL 260926-001'],
    ['/twa/exec/tasks/260926-001?action=done', 'EXEC-REPORT 260926-001'],
  ])('simple_mode=false: %s → %s', async (path, expected) => {
    mockProfile(false)
    renderAt(path)
    expect(await screen.findByText(expected)).toBeInTheDocument()
  })

  it('первый вход в простой режим — сначала язык, затем туда, куда шли', async () => {
    resetLangChosenForTests()
    mockProfile(true)
    renderAt('/twa/exec/tasks/260926-001?action=done')
    expect(
      await screen.findByText(`SIMPLE-LANG?next=${encodeURIComponent('/twa/s/task/260926-001/done')}`),
    ).toBeInTheDocument()
  })
})
