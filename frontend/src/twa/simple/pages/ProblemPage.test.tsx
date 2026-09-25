import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { Routes, Route } from 'react-router'
import { render, screen, fireEvent, waitFor } from '../../../test/test-utils'
import { stubTelegram, unstubTelegram } from '../../../test/twaSimple'
import ProblemPage from './ProblemPage'

// «Проблема»: шаблон (имена — Literal ProblemBody) + необязательный текст,
// подтверждение «Да / Нет» перед отправкой.

const { mockPost } = vi.hoisted(() => ({ mockPost: vi.fn() }))
vi.mock('../../twaClient', () => ({ twaClient: { get: vi.fn(), post: mockPost, patch: vi.fn() } }))

const NUMBER = '260926-008'

beforeEach(() => {
  mockPost.mockReset()
  mockPost.mockResolvedValue({ data: {} })
})

afterEach(() => unstubTelegram())

function renderProblem() {
  return render(
    <Routes>
      <Route path="/twa/s/task/:number/problem" element={<ProblemPage />} />
      <Route path="/twa/s/task/:number" element={<div>TASK</div>} />
    </Routes>,
    { routerEntries: [`/twa/s/task/${NUMBER}/problem`] },
  )
}

describe('ProblemPage', () => {
  it('шаблон → «Да» → POST /problem {template}; успех — галка и вибрация success', async () => {
    const { haptic } = stubTelegram()
    renderProblem()
    fireEvent.click(screen.getByRole('button', { name: /Не пустили/ }))
    expect(screen.getByRole('dialog', { name: 'Отправить менеджеру?' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Да/ }))
    await waitFor(() =>
      expect(mockPost).toHaveBeenCalledWith(`/api/v2/requests/${NUMBER}/problem`, { template: 'not_let_in' }),
    )
    expect(await screen.findByText('Менеджер получил')).toBeInTheDocument()
    expect(haptic.notificationOccurred).toHaveBeenCalledWith('success')
  })

  it('«Написать» добавляет текст к шаблону', async () => {
    renderProblem()
    fireEvent.click(screen.getByRole('button', { name: /Написать/ }))
    fireEvent.change(screen.getByPlaceholderText('Что случилось?'), { target: { value: '  Нужна краска  ' } })
    expect(screen.getByText('Выберите, что случилось')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Нет материала/ }))
    // Текст виден в подтверждении.
    expect(screen.getByRole('dialog')).toHaveTextContent('Нужна краска')
    fireEvent.click(screen.getByRole('button', { name: /Да/ }))
    await waitFor(() =>
      expect(mockPost).toHaveBeenCalledWith(`/api/v2/requests/${NUMBER}/problem`, {
        template: 'no_material',
        text: 'Нужна краска',
      }),
    )
  })

  it('«Нет» — ничего не отправляется', () => {
    renderProblem()
    fireEvent.click(screen.getByRole('button', { name: /Нужен мастер/ }))
    fireEvent.click(screen.getByRole('button', { name: /Нет$/ }))
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(mockPost).not.toHaveBeenCalled()
  })

  it('409 — «Заявка уже закрыта» без сырого detail', async () => {
    mockPost.mockRejectedValue({ response: { status: 409, data: { detail: 'invalid_status' } } })
    renderProblem()
    fireEvent.click(screen.getByRole('button', { name: /Жителя нет дома/ }))
    fireEvent.click(screen.getByRole('button', { name: /Да/ }))
    expect(await screen.findByText('Заявка уже закрыта')).toBeInTheDocument()
    expect(screen.queryByText('invalid_status')).toBeNull()
  })
})
