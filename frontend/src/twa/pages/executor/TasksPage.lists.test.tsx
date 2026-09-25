import { describe, it, expect, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { render, screen, within } from '../../../test/test-utils'
import { server } from '../../../test/msw/server'

vi.mock('../../hooks/useTelegramSDK', () => ({
  useTelegramSDK: () => ({ haptic: vi.fn(), showBackButton: () => () => {} }),
}))

import TasksPage from './TasksPage'
import ArchivePage from './ArchivePage'
import PurchasePage from './PurchasePage'

const base = { category: 'Сантехника', description: 'x', created_at: '2026-09-23T10:00:00Z' }
const IN_WORK = { ...base, request_number: '260923-001', status: 'В работе' }
const RETURNED = {
  ...base, request_number: '260923-002', status: 'Возвращена', return_reason: 'Опять капает',
}

function seedList(rows: unknown[]) {
  server.use(http.get('*/api/v2/requests', () => HttpResponse.json(rows)))
}

describe('TWA исполнитель — «Возвращена» в «Заданиях»', () => {
  it('возвращённая жителем заявка видна отдельной группой ВВЕРХУ, с причиной возврата', async () => {
    seedList([IN_WORK, RETURNED])
    render(<TasksPage />)
    const headers = await screen.findAllByRole('heading', { level: 2 })
    expect(headers[0]).toHaveTextContent('Возвращена (1)')
    expect(screen.getByText('260923-002')).toBeInTheDocument()
    expect(screen.getByText(/Опять капает/)).toBeInTheDocument()
    expect(screen.getByText(/Менеджер решит/)).toBeInTheDocument()
  })
})

describe('TWA исполнитель — ошибка загрузки ≠ пустой список', () => {
  const pages = [
    ['Задания', TasksPage, 'Нет активных заданий'],
    ['Закуп', PurchasePage, 'Нет заявок на закуп'],
    ['Архив', ArchivePage, 'Архив пуст'],
  ] as const

  for (const [name, Page, emptyText] of pages) {
    it(`${name}: сетевая ошибка → текст ошибки + «Повторить» (refetch), без пустого состояния`, async () => {
      let calls = 0
      server.use(http.get('*/api/v2/requests', () => {
        calls += 1
        return calls === 1 ? HttpResponse.error() : HttpResponse.json([])
      }))
      const user = userEvent.setup()
      render(<Page />)
      const alert = await screen.findByRole('alert')
      expect(within(alert).getByText('Не удалось загрузить список')).toBeInTheDocument()
      expect(screen.queryByText(emptyText)).toBeNull()

      await user.click(within(alert).getByRole('button', { name: 'Повторить' }))
      expect(await screen.findByText(emptyText)).toBeInTheDocument()
      expect(calls).toBe(2)
      expect(screen.queryByRole('alert')).toBeNull()
    })
  }
})

describe('TWA исполнитель — сервер фильтрует статусы (лимит 50 не съедает активные)', () => {
  function captureQuery() {
    const seen: URLSearchParams[] = []
    server.use(http.get('*/api/v2/requests', ({ request }) => {
      seen.push(new URL(request.url).searchParams)
      return HttpResponse.json([])
    }))
    return seen
  }

  it('«Задания» запрашивают только активные статусы, повторяемым status', async () => {
    const seen = captureQuery()
    render(<TasksPage />)
    await screen.findByText('Нет активных заданий')
    const q = seen[0]
    expect(q.get('view')).toBe('assigned')
    expect(q.getAll('status')).toEqual(['Возвращена', 'В работе', 'Закуп', 'Уточнение', 'Новая'])
  })

  it('«Архив» запрашивает только архивные статусы', async () => {
    const seen = captureQuery()
    render(<ArchivePage />)
    await screen.findByText('Архив пуст')
    expect(seen[0].getAll('status')).toEqual(['Выполнена', 'Исполнено', 'Принято', 'Отменена'])
  })
})
