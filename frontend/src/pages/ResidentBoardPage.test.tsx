import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen } from '../test/test-utils'
import { DEFAULT_DISPLAY_TZ, setDisplayTz } from '../utils/timezone'
import { DisplayTzContext } from '../contexts/displayTz'
import { defaultBoardConfig } from '../types/boardConfig'
import type { BoardConfigData } from '../types/boardConfig'
import { http, HttpResponse } from 'msw'
import { server } from '../test/msw/server'
import ResidentBoardPage from './ResidentBoardPage'

// jsdom: matchMedia всегда false → ТВ-раскладка недостижима; считаем экран большим.
vi.mock('../hooks/useMediaQuery', () => ({ useMediaQuery: () => true }))

// T16 — модуль «Лифты» регистрируется в MODULES только под VITE_ELEVATORS_ENABLED:
// без флага даже видимая layout-запись "elevators" ничего не рендерит.

function configWithElevators(): BoardConfigData {
  const cfg = JSON.parse(JSON.stringify(defaultBoardConfig)) as BoardConfigData
  cfg.layout = [...cfg.layout, { id: 'elevators', visible: true, width: 'full' }]
  cfg.elevators = { title: { ru: 'Наши лифты', uz: 'Liftlarimiz' } }
  return cfg
}

beforeEach(() => {
  vi.unstubAllEnvs()
})

// A9-P3-19 (класс ARCH-116): часы и дата табло шли по зоне браузера (киоск/ТВ с
// неверной зоной показывал чужое время). Display-зона +14: 10:30Z = 00:30 след.
// суток — старый код совпадал бы с этим только на раннере в +14.
describe('ResidentBoardPage — часы в display-зоне', () => {
  afterEach(() => {
    setDisplayTz(DEFAULT_DISPLAY_TZ)
    vi.useRealTimers()
  })

  it('часы и дата — стенка display-зоны, а не браузера', async () => {
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date('2026-06-05T10:30:00Z'))
    setDisplayTz('Pacific/Kiritimati')
    render(<DisplayTzContext.Provider value="Pacific/Kiritimati"><ResidentBoardPage configOverride={JSON.parse(JSON.stringify(defaultBoardConfig))} /></DisplayTzContext.Provider>)
    expect(await screen.findByText('00:30')).toBeInTheDocument()
    expect(screen.getByText(/Суббота, 6 /)).toBeInTheDocument()
  })
})

describe('ResidentBoardPage — модуль «Лифты»', () => {
  it('рендерит модуль с заголовком из конфига при включённом флаге', async () => {
    vi.stubEnv('VITE_ELEVATORS_ENABLED', 'true')
    render(<ResidentBoardPage configOverride={configWithElevators()} />)
    expect(await screen.findByText('Наши лифты')).toBeInTheDocument()
    expect(await screen.findByText('Данные о лифтах пока не опубликованы')).toBeInTheDocument()
  })

  it('не регистрирует модуль без флага, даже если layout его включает', async () => {
    vi.stubEnv('VITE_ELEVATORS_ENABLED', '')
    render(<ResidentBoardPage configOverride={configWithElevators()} />)
    expect(await screen.findByText('Текущие заявки')).toBeInTheDocument()
    expect(screen.queryByText('Наши лифты')).not.toBeInTheDocument()
    expect(screen.queryByText('Данные о лифтах пока не опубликованы')).not.toBeInTheDocument()
  })
})

// «Выполнено за месяц» на табло суммировало status_counts без даты (все решённые
// за всё время), тогда как главная жителей показывала completed_month за бизнес-месяц.
// Табло берёт ту же цифру API.
describe('ResidentBoardPage — «Выполнено за месяц»', () => {
  it('показывает completed_month, а не сумму status_counts', async () => {
    server.use(
      http.get('*/api/v2/public/board', () =>
        HttpResponse.json({
          status_counts: { 'Выполнена': 100, 'Исполнено': 100, 'Принято': 51 },
          completed_month: 182,
          active_requests: [], active_executors: 0, avg_resolution_hours: null, avg_rating: null,
        }),
      ),
    )
    render(<ResidentBoardPage configOverride={defaultBoardConfig} />)
    expect(await screen.findByText('182')).toBeInTheDocument()
    expect(screen.queryByText('251')).not.toBeInTheDocument()
  })
})

// ТВ-режим — только по кнопке/ссылке ?mode=tv, не автоматически по размеру экрана.
describe('ResidentBoardPage — ТВ-режим по кнопке', () => {
  // Без configOverride (он выключает ТВ и кнопку — режим превью редактора) страница ждёт board-config с сервера.
  beforeEach(() => {
    server.use(http.get('*/api/v2/public/board-config', () => HttpResponse.json(defaultBoardConfig)))
  })

  it('большой экран без ?mode=tv — обычная страница с кнопкой «Для экрана»', async () => {
    render(<ResidentBoardPage />, { routerEntries: ['/resident-board'] })
    expect(await screen.findByText('Текущие заявки')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Для экрана' })).toHaveAttribute('href', '/resident-board?mode=tv')
    expect(document.querySelector('.rb-tv')).toBeNull()
  })

  it('?mode=tv — ТВ-раскладка со ссылкой назад на обычную версию', async () => {
    render(<ResidentBoardPage />, { routerEntries: ['/resident-board?mode=tv'] })
    expect(await screen.findByRole('link', { name: 'Обычная версия' })).toHaveAttribute('href', '/resident-board')
    expect(document.querySelector('.rb-tv')).not.toBeNull()
  })
})
