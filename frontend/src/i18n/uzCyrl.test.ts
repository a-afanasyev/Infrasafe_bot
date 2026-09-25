import { afterAll, describe, expect, it } from 'vitest'
import i18n, { toBcp47, UZ_CYRL, uzCyrl } from './index'
import { formatDate, formatNumber } from './formatters'
import uz from './locales/uz.json'
import { stripProtected } from './uzTranslit'

// Третья локаль — узбекская кириллица (users.language = uz_cyrl) =
// транслитерация всего uz.json + ручные правки uz_cyrl.json. На экране одна
// письменность; язык не пишется в общий с дашбордом ключ localStorage.

function leafKeys(obj: unknown, prefix = ''): string[] {
  if (!obj || typeof obj !== 'object') return [prefix]
  return Object.entries(obj as Record<string, unknown>).flatMap(([k, v]) =>
    leafKeys(v, prefix ? `${prefix}.${k}` : k),
  )
}

function leafValues(obj: unknown): string[] {
  if (typeof obj === 'string') return [obj]
  if (!obj || typeof obj !== 'object') return []
  return Object.values(obj as Record<string, unknown>).flatMap(leafValues)
}

afterAll(async () => {
  await i18n.changeLanguage('ru')
})

describe('uz_cyrl locale', () => {
  it('содержит все ключи uz', () => {
    expect(leafKeys(uzCyrl).sort()).toEqual(leafKeys(uz).sort())
  })

  it('общие ключи тоже кириллицей (не смесь письменностей)', async () => {
    await i18n.changeLanguage(UZ_CYRL)
    expect(i18n.t('twa.simple.task.done')).toBe('Тайёр')
    expect(i18n.t('twa.simple.tabs.mine')).toBe('Аризаларим')
    expect(i18n.t('twa.exec.shift.title')).toBe('Смена')
    expect(i18n.t('twa.errors.generic')).toBe('Хатолик юз берди')
    expect(i18n.t('twa.simple.pendingPhotos', { count: 2 })).toBe('Юборилмаган сурат: 2')
    const latin = leafValues((uzCyrl as { twa: unknown }).twa).filter((s) => /[A-Za-z]/.test(stripProtected(s)))
    expect(latin).toEqual([])
    expect(document.documentElement.lang).toBe('uz-Cyrl')
  })

  it('uz_cyrl не сохраняется в общий ключ localStorage дашборда', async () => {
    await i18n.changeLanguage('ru')
    expect(window.localStorage.getItem('i18nextLng')).toBe('ru')
    await i18n.changeLanguage(UZ_CYRL)
    expect(window.localStorage.getItem('i18nextLng')).toBe('ru')
  })

  it('форматтеры не падают на uz_cyrl (Intl не принимает подчёркивание)', async () => {
    await i18n.changeLanguage(UZ_CYRL)
    expect(formatNumber(1234)).toBeTruthy()
    expect(formatDate('2026-09-26T10:00:00Z')).toBeTruthy()
    expect(toBcp47('ru')).toBe('ru')
  })
})
