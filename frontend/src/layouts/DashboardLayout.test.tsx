import { describe, it, expect, beforeEach } from 'vitest'
import userEvent from '@testing-library/user-event'
import { Routes, Route } from 'react-router'
import { render, screen } from '../test/test-utils'
import DashboardLayout from './DashboardLayout'
import { useAuthStore } from '../stores/authStore'
import { useNameCaseStore } from '../stores/nameCaseStore'
import { actionsFor } from '../test/authz'

// TEST-068 Phase 3: каркас дашборда был 0 строк покрытия, при том что в нём
// живёт ролевой гейтинг навигации (isVisibleTo) — регресс тут прячет целые
// разделы у менеджера или, наоборот, показывает их не тем ролям.

function renderLayout(route = '/dashboard') {
  return render(
    <Routes>
      <Route path="/dashboard" element={<DashboardLayout />}>
        <Route index element={<div data-testid="page-body">outlet-контент</div>} />
        {/* любой вложенный маршрут — чтобы проверять авто-раскрытие групп по активному пути */}
        <Route path="*" element={<div data-testid="page-body">outlet-контент</div>} />
      </Route>
    </Routes>,
    { routerEntries: [route] },
  )
}

function login(roles: string[]) {
  useAuthStore.setState({
    user: {
      id: 1, first_name: 'Мария', roles, actions: actionsFor(roles),
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

// Группа «Настройки» (витрина, роли, группы, отключения, правила ИИ) свёрнута,
// пока активный маршрут не внутри неё — раскрываем кликом по заголовку.
async function openSettings() {
  await userEvent.click(screen.getByRole('button', { name: /настройки/i }))
}

describe('DashboardLayout — навигация и роли', () => {
  it('рендерит каркас и контент вложенного маршрута', () => {
    renderLayout()
    expect(screen.getByTestId('page-body')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /заявки/i })).toBeInTheDocument()
  })

  it('менеджер видит «Жители», а «Группы» — внутри группы «Настройки»', async () => {
    renderLayout()
    expect(screen.getByRole('link', { name: /жители/i })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /группы/i })).not.toBeInTheDocument()   // свёрнуто
    await openSettings()
    expect(screen.getByRole('link', { name: /группы/i })).toBeInTheDocument()
  })

  it('«Настройки» раскрываются и содержат витрину, роли, группы и правила ИИ', async () => {
    renderLayout()
    await openSettings()
    expect(screen.getByRole('link', { name: /витрин/i })).toHaveAttribute('href', '/dashboard/board-editor')
    expect(screen.getByRole('link', { name: /роли и права/i })).toHaveAttribute('href', '/dashboard/roles')
    expect(screen.getByRole('link', { name: /группы/i })).toHaveAttribute('href', '/dashboard/groups')
    expect(screen.getByRole('link', { name: /правила ии/i })).toHaveAttribute('href', '/dashboard/ai-manager')
  })

  it('группа «Настройки» раскрыта, когда активен её маршрут', () => {
    renderLayout('/dashboard/ai-manager')
    expect(screen.getByRole('link', { name: /правила ии/i })).toBeInTheDocument()
  })

  it('без прав на разделы настроек группы «Настройки» нет вовсе', () => {
    login(['executor'])
    renderLayout()
    expect(screen.queryByRole('button', { name: /настройки/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /правила ии/i })).not.toBeInTheDocument()
  })

  it('без роли manager «Жители» и «Группы» скрыты, общие пункты остаются', () => {
    login(['executor'])
    renderLayout()
    expect(screen.queryByRole('link', { name: /жители/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /группы/i })).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: /заявки/i })).toBeInTheDocument()
  })

  it('инженер видит доску и аналитику, но не разделы персонала, смен, адресов и модерации', () => {
    login(['executor', 'engineer'])
    renderLayout()
    expect(screen.getByRole('link', { name: /заявки/i })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /аналитика/i })).toBeInTheDocument()
    for (const name of [/адреса/i, /витрин/i, /обратная связь/i]) {
      expect(screen.queryByRole('link', { name })).not.toBeInTheDocument()
    }
    // группа «Персонал» (сотрудники, смены, шаблоны) пуста — не видна вовсе
    expect(screen.queryByText('Персонал')).not.toBeInTheDocument()
  })

  it('менеджер по-прежнему видит все свои разделы', async () => {
    renderLayout()
    for (const name of [/аналитика/i, /адреса/i, /обратная связь/i]) {
      expect(screen.getByRole('link', { name })).toBeInTheDocument()
    }
    expect(screen.getByText('Персонал')).toBeInTheDocument()
    await openSettings()
    expect(screen.getByRole('link', { name: /витрин/i })).toBeInTheDocument()
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
