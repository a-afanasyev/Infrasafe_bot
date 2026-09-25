import { describe, it, expect, beforeEach, afterAll, vi } from 'vitest'
import { Routes, Route } from 'react-router'
import { render, screen, fireEvent, waitFor, testI18n } from '../../../test/test-utils'
import { isLangChosen, resetLangChosenForTests, safeNext } from '../langFlag'
import LangPage from './LangPage'

// Выбор языка простого режима: три кнопки-самоназвания, PATCH /profile,
// флаг «уже спросили», возврат на экран, с которого увели.

const { mockPatch } = vi.hoisted(() => ({ mockPatch: vi.fn() }))
vi.mock('../../twaClient', () => ({ twaClient: { get: vi.fn(), post: vi.fn(), patch: mockPatch } }))

beforeEach(() => {
  resetLangChosenForTests()
  mockPatch.mockReset()
  mockPatch.mockResolvedValue({ data: {} })
})

afterAll(async () => {
  resetLangChosenForTests()
  await testI18n.changeLanguage('ru')
})

function renderLang(next = '/twa/s/task/260926-001/done') {
  return render(
    <Routes>
      <Route path="/twa/s/lang" element={<LangPage />} />
      <Route path="/twa/s/task/:number/done" element={<div>DONE SCREEN</div>} />
      <Route path="/twa/s" element={<div>MINE</div>} />
    </Routes>,
    { routerEntries: [`/twa/s/lang?next=${encodeURIComponent(next)}`] },
  )
}

describe('LangPage', () => {
  it('три кнопки и больше ни одной подписи', () => {
    renderLang()
    expect(screen.getAllByRole('button').map((b) => b.textContent)).toEqual(['O‘zbekcha', 'Ўзбекча', 'Русский'])
  })

  it('«Ўзбекча» → PATCH language=uz_cyrl, флаг, возврат на next', async () => {
    renderLang()
    fireEvent.click(screen.getByRole('button', { name: 'Ўзбекча' }))
    await waitFor(() => expect(mockPatch).toHaveBeenCalledWith('/api/v2/profile', { language: 'uz_cyrl' }))
    expect(await screen.findByText('DONE SCREEN')).toBeInTheDocument()
    expect(isLangChosen()).toBe(true)
    expect(testI18n.language).toBe('uz_cyrl')
  })

  it('чужой next игнорируется — на «Мои»', async () => {
    renderLang('https://evil.example/x')
    fireEvent.click(screen.getByRole('button', { name: 'Русский' }))
    expect(await screen.findByText('MINE')).toBeInTheDocument()
  })

  it('ошибка сохранения — крест на весь экран, флаг не ставится; «Ещё раз» повторяет выбор', async () => {
    mockPatch.mockRejectedValueOnce({ response: { status: 500 } })
    renderLang()
    fireEvent.click(screen.getByRole('button', { name: 'O‘zbekcha' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Язык не сохранился')
    expect(isLangChosen()).toBe(false)
    fireEvent.click(screen.getByRole('button', { name: /Ещё раз/ }))
    await waitFor(() => expect(mockPatch).toHaveBeenLastCalledWith('/api/v2/profile', { language: 'uz' }))
    expect(await screen.findByText('DONE SCREEN')).toBeInTheDocument()
  })

  it.each([
    ['/twa/s/../app', '/twa/s'],
    ['/twa/s/./pool', '/twa/s'],
    ['/twa/s/lang?next=x', '/twa/s'],
    ['//evil.example', '/twa/s'],
    ['/twa/s/task/1/done', '/twa/s/task/1/done'],
    ['/twa/s?x=1', '/twa/s?x=1'],
  ])('safeNext(%s) → %s', (next, expected) => {
    expect(safeNext(next)).toBe(expected)
  })
})
