import { describe, it, expect, afterEach, vi } from 'vitest'
import { defaultBoardConfig, defaultHomeConfig } from '../../types/boardConfig'
import type { BoardConfigData, HomeBlockCfg } from '../../types/boardConfig'
import { resolveHomeBlocks } from './homeConfig'

function config(home: BoardConfigData['home']): BoardConfigData {
  return { ...JSON.parse(JSON.stringify(defaultBoardConfig)), home }
}

function withBlocks(blocks: HomeBlockCfg[]): BoardConfigData {
  return config({ ...defaultHomeConfig, blocks })
}

afterEach(() => vi.unstubAllEnvs())

describe('resolveHomeBlocks', () => {
  it('без home (старый бэкенд) — видны все блоки включённых модулей', () => {
    vi.stubEnv('VITE_ELEVATORS_ENABLED', 'true')
    vi.stubEnv('VITE_WORK_REPORTS_ENABLED', 'true')
    const blocks = resolveHomeBlocks(config(undefined), 'ru')
    expect(Object.values(blocks).every((b) => b.visible)).toBe(true)
  })

  it('модуль выключен на фронте — блок скрыт, даже если в конфиге видим', () => {
    vi.stubEnv('VITE_ELEVATORS_ENABLED', '')
    vi.stubEnv('VITE_WORK_REPORTS_ENABLED', 'true')
    const blocks = resolveHomeBlocks(config(defaultHomeConfig), 'ru')
    expect(blocks.elevators.visible).toBe(false)
    expect(blocks.workreports.visible).toBe(true)
  })

  it('блока нет в ответе (бэкенд вырезал флагом) — скрыт', () => {
    vi.stubEnv('VITE_ELEVATORS_ENABLED', 'true')
    const blocks = resolveHomeBlocks(withBlocks(defaultHomeConfig.blocks.filter((b) => b.id !== 'elevators')), 'ru')
    expect(blocks.elevators.visible).toBe(false)
    expect(blocks.requests.visible).toBe(true)
  })

  it('видимость и свой заголовок из конфига, с откатом на ru', () => {
    const blocks = resolveHomeBlocks(
      withBlocks(defaultHomeConfig.blocks.map((b) =>
        b.id === 'works' ? { ...b, visible: false } : b.id === 'requests' ? { ...b, title: { ru: ' Заявки ЖК ', uz: '' } } : b,
      )),
      'uz',
    )
    expect(blocks.works.visible).toBe(false)
    expect(blocks.requests.title).toBe('Заявки ЖК')
    expect(blocks.contacts.title).toBe('')
  })
})
