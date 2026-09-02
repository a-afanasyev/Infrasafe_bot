import { describe, it, expect, beforeEach } from 'vitest'
import userEvent from '@testing-library/user-event'
import { Routes, Route } from 'react-router'
import { render, screen } from '../test/test-utils'
import DashboardLayout from './DashboardLayout'
import { useAuthStore } from '../stores/authStore'
import { useNameCaseStore } from '../stores/nameCaseStore'

// TEST-068 Phase 3: каркас дашборда был 0 строк покрытия, при том что в нём
// живёт ролевой гейтинг навигации (isVisibleTo) — регресс тут прячет целые
// разделы у менеджера или, наоборот, показывает их не тем ролям.

function renderLayout(route = '/dashboard') {
  return render(
    <Routes>
      <Route path="/dashboard" element={<DashboardLayout />}>
        <Route index element={<div data-testid="page-body">outlet-контент</div>} />
      </Route>
    </Routes>,
    { routerEntries: [route] },
  )
}

function login(roles: string[]) {
  useAuthStore.setState({
    user: {
      id: 1, first_name: 'Мария', roles,
    } as never,
    isAuthenticated: true,
  })
}

beforeEach(() => {
  localStorage.clear()
  useNameCaseStore.setState({ mode: 'title' })
  login(['manager'])
  // Глобальный стаб setup.ts всегда отвечает matches:false → лэйаут считает
  // окно мобильным и прячет сайдбар. Здесь предмет — десктопная навигация.
  window.matchMedia = ((query: string) => ({
    matches: query.includes('min-width'),
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  })) as typeof window.matchMedia
})

function userMenuTrigger() {
  const trigger = screen
    .getAllByRole('button')
    .find(b => b.getAttribute('aria-haspopup') === 'true')
  expect(trigger).toBeDefined()
  return trigger!
}

describe('DashboardLayout — навигация и роли', () => {
  it('рендерит каркас и контент вложенного маршрута', () => {
    renderLayout()
    expect(screen.getByTestId('page-body')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /заявки/i })).toBeInTheDocument()
  })

  it('менеджер видит «Жители» и «Группы»', () => {
    renderLayout()
    expect(screen.getByRole('link', { name: /жители/i })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /группы/i })).toBeInTheDocument()
  })

  it('без роли manager «Жители» и «Группы» скрыты, общие пункты остаются', () => {
    login(['executor'])
    renderLayout()
    expect(screen.queryByRole('link', { name: /жители/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /группы/i })).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: /адреса/i })).toBeInTheDocument()
  })

  it('«Склад» виден только ролям модуля материалов', () => {
    login(['executor'])
    const first = renderLayout()
    expect(screen.queryByRole('link', { name: /склад/i })).not.toBeInTheDocument()
    first.unmount()
    login(['manager'])
    renderLayout()
    expect(screen.getByRole('link', { name: /склад/i })).toBeInTheDocument()
  })
})

describe('DashboardLayout — меню пользователя', () => {
  it('раскрывается по клику и показывает пункт выхода', async () => {
    renderLayout()
    const trigger = userMenuTrigger()
    await userEvent.click(trigger)
    expect(trigger).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByText(/выйти|выход/i)).toBeInTheDocument()
  })

  it('Escape закрывает меню', async () => {
    renderLayout()
    const trigger = userMenuTrigger()
    await userEvent.click(trigger)
    await userEvent.keyboard('{Escape}')
    expect(trigger).toHaveAttribute('aria-expanded', 'false')
  })

  // Предпочтение «ФИО заглавными буквами»: чекбокс в меню, пишет в
  // localStorage, меню не закрывает, имя в шапке меню сразу капсится.
  it('галочка «ФИО заглавными» переключает режим и сохраняет его', async () => {
    renderLayout()
    await userEvent.click(userMenuTrigger())
    const toggle = screen.getByRole('menuitemcheckbox', { name: /ФИО заглавными/i })
    expect(toggle).toHaveAttribute('aria-checked', 'false')
    expect(screen.getByText('Мария')).toBeInTheDocument()

    await userEvent.click(toggle)
    expect(toggle).toHaveAttribute('aria-checked', 'true')
    expect(localStorage.getItem('uk.nameCase')).toBe('caps')
    expect(screen.getByText('МАРИЯ')).toBeInTheDocument()

    await userEvent.click(toggle)
    expect(toggle).toHaveAttribute('aria-checked', 'false')
    expect(screen.getByText('Мария')).toBeInTheDocument()
  })
})
