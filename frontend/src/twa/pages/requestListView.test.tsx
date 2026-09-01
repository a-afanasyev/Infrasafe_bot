import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, waitFor } from '../../test/test-utils'
import RequestsPage from './applicant/RequestsPage'
import TasksPage from './executor/TasksPage'
import type { ReactElement } from 'react'

// Регрессия 2026-09-01: TWA слал мёртвый `scope=my`, сервер решал по ролям —
// менеджер-житель видел весь ЖК в «Моих заявках», исполнитель-житель не видел
// своих поданных. Теперь раздел жителя явно просит `view=own`, раздел
// исполнителя — `view=assigned`; `scope` из контракта удалён.
const { mockGet } = vi.hoisted(() => ({ mockGet: vi.fn() }))

vi.mock('../twaClient', () => ({
  twaClient: { get: mockGet, patch: vi.fn(), post: vi.fn() },
}))

beforeEach(() => {
  mockGet.mockReset()
  mockGet.mockResolvedValue({ data: [] })
})

async function paramsSentBy(ui: ReactElement) {
  render(ui)
  await waitFor(() => expect(mockGet).toHaveBeenCalled())
  const call = mockGet.mock.calls.find(([url]) => url === '/api/v2/requests')
  expect(call, 'ожидался GET /api/v2/requests').toBeDefined()
  return call![1]?.params ?? {}
}

describe('TWA-списки заявок шлют явный view', () => {
  it('раздел жителя — view=own', async () => {
    const params = await paramsSentBy(<RequestsPage />)
    expect(params).toMatchObject({ view: 'own' })
    expect(params).not.toHaveProperty('scope')
  })

  it('раздел исполнителя — view=assigned', async () => {
    const params = await paramsSentBy(<TasksPage />)
    expect(params).toMatchObject({ view: 'assigned' })
    expect(params).not.toHaveProperty('scope')
  })
})
