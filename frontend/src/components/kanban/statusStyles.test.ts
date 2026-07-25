import { describe, expect, it } from 'vitest'
import { STATUS_MAP } from '../../i18n/apiMaps'
import { STATUS_BADGE, STATUS_DOT } from './statusStyles'

// Прод-баг (AUD5-APIFE-16): карты цветов статусов жили в ДВУХ копиях —
// `KanbanColumn.tsx` и `RequestDetailModal.tsx`. PR7 добавил «Возвращена»
// только в первую, вторая осталась с восемью статусами, и карточка возврата
// показывала серый бейдж без подписи цвета. До 2026-07-25 это почти не
// стреляло (в «Возвращена» попадали редко), но PR #256 включил возврат из
// TWA-приёмки — статус стал штатным, и дефект вышел к менеджерам.
//
// Отсюда форма фикса: одна карта на оба места + `Record<ApiStatus, …>`,
// который роняет `tsc -b` при следующем новом статусе. Этот тест — второй
// контур: он ловит и «ключ есть, но пустая строка», чего тип не видит.
describe('status style maps cover the API status canon', () => {
  const statuses = Object.keys(STATUS_MAP)

  it.each(statuses)('«%s» has a badge style', (status) => {
    const style = STATUS_BADGE[status as keyof typeof STATUS_BADGE]
    expect(style?.bg).toBeTruthy()
    expect(style?.text).toBeTruthy()
  })

  it.each(statuses)('«%s» has a dot colour', (status) => {
    expect(STATUS_DOT[status as keyof typeof STATUS_DOT]).toBeTruthy()
  })

  it('carries no keys outside the canon (иначе карта переживёт статус)', () => {
    expect(Object.keys(STATUS_BADGE).sort()).toEqual(statuses.sort())
    expect(Object.keys(STATUS_DOT).sort()).toEqual(statuses.sort())
  })
})

describe('«Возвращена» — исходный дефект', () => {
  it('is styled, not left to the neutral fallback', () => {
    expect(STATUS_BADGE['Возвращена']).toBeDefined()
    expect(STATUS_DOT['Возвращена']).toBeDefined()
  })

  it('reads visually distinct from «Исполнено» — возврат не должен выглядеть как успех', () => {
    expect(STATUS_DOT['Возвращена']).not.toBe(STATUS_DOT['Исполнено'])
    expect(STATUS_BADGE['Возвращена'].bg).not.toBe(STATUS_BADGE['Исполнено'].bg)
  })
})
