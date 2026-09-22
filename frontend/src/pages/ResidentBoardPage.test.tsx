import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen } from '../test/test-utils'
import { DEFAULT_DISPLAY_TZ, setDisplayTz } from '../utils/timezone'
import { defaultBoardConfig } from '../types/boardConfig'
import type { BoardConfigData } from '../types/boardConfig'
import ResidentBoardPage from './ResidentBoardPage'

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
    render(<ResidentBoardPage configOverride={JSON.parse(JSON.stringify(defaultBoardConfig))} />)
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
