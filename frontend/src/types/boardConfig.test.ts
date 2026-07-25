import { describe, it, expect } from 'vitest'
import { MODULE_IDS, defaultBoardConfig } from './boardConfig'

// Зеркалит uk_management_bot/api/board_config/defaults.py ALL_MODULE_IDS.
// Правка одной стороны без другой не поймается тайпчекером — ловит только
// этот тест.
const BACKEND_ALL_MODULE_IDS = ['stats', 'requests', 'announcements', 'rating', 'hours', 'workreports']

describe('MODULE_IDS parity with backend ALL_MODULE_IDS', () => {
  it('matches the backend tuple exactly, including order', () => {
    expect(MODULE_IDS).toEqual(BACKEND_ALL_MODULE_IDS)
  })
})

describe('defaultBoardConfig.layout', () => {
  it('covers the 5 pre-work-reports modules, deliberately excluding workreports', () => {
    const ids = defaultBoardConfig.layout.map((item) => item.id)
    expect(ids).toEqual(['stats', 'requests', 'announcements', 'rating', 'hours'])
  })

  it('every layout item has a valid width', () => {
    for (const item of defaultBoardConfig.layout) {
      expect(['full', 'half']).toContain(item.width)
    }
  })
})

describe('defaultBoardConfig.work_reports', () => {
  it('matches the backend default shape', () => {
    expect(defaultBoardConfig.work_reports).toEqual({
      autopost: false,
      autopost_since: null,
      limit: 6,
      title: { ru: 'Отчёты о выполненных работах', uz: 'Bajarilgan ishlar hisobotlari' },
    })
  })
})
