import { describe, it, expect } from 'vitest'
import { MODULE_IDS, defaultBoardConfig, toEditableBoardConfig } from './boardConfig'
import type { BoardConfigResponse } from './boardConfig'

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
      // Публикация без модерации — выключена по умолчанию; пустой список
      // категорий = без ограничения (см. WorkReportsCfg на бэкенде).
      autopublish: false,
      categories: [],
      autopost_since: null,
      limit: 6,
      title: { ru: 'Отчёты о выполненных работах', uz: 'Bajarilgan ishlar hisobotlari' },
    })
  })
})

// ARCH-137 B5: PUT-схема бэка строгая (extra="forbid") — echo display_tz из
// ответа при сохранении витрины = 422. toEditableBoardConfig — единственный
// легальный путь «ответ → редактируемый draft», и он обязан снимать поле.
describe('toEditableBoardConfig', () => {
  const response: BoardConfigResponse = {
    ...JSON.parse(JSON.stringify(defaultBoardConfig)),
    display_tz: 'Asia/Tashkent',
  }

  it('strips display_tz — иначе PUT редактора получит 422 от строгой схемы', () => {
    const editable = toEditableBoardConfig(response)
    expect('display_tz' in editable).toBe(false)
    expect(editable).toEqual(defaultBoardConfig)
  })

  it('deep-copies: мутация draft не трогает объект ответа (кэш react-query)', () => {
    const editable = toEditableBoardConfig(response)
    editable.org.name.ru = 'мутировано'
    expect(response.org.name.ru).toBe(defaultBoardConfig.org.name.ru)
  })

  it('терпит ответ без display_tz (rolling deploy: бэкенд ещё старый)', () => {
    const legacy = JSON.parse(JSON.stringify(defaultBoardConfig))
    expect(toEditableBoardConfig(legacy)).toEqual(defaultBoardConfig)
  })
})
