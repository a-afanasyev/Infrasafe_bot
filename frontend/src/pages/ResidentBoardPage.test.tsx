import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen } from '../test/test-utils'
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
