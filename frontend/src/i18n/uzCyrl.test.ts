import { afterAll, describe, expect, it } from 'vitest'
import i18n, { toBcp47, UZ_CYRL } from './index'
import { formatDate, formatNumber } from './formatters'
import ru from './locales/ru.json'
import uz from './locales/uz.json'
import uzCyrl from './locales/uz_cyrl.json'

// Третья локаль — узбекская кириллица (users.language = uz_cyrl). Переведён
// только простой режим исполнителя; всё прочее i18next берёт из uz, затем ru.

function leafKeys(obj: unknown, prefix = ''): string[] {
  if (!obj || typeof obj !== 'object') return [prefix]
  return Object.entries(obj as Record<string, unknown>).flatMap(([k, v]) =>
    leafKeys(v, prefix ? `${prefix}.${k}` : k),
  )
}

afterAll(async () => {
  await i18n.changeLanguage('ru')
})

describe('uz_cyrl locale', () => {
  it('содержит все ключи twa.simple.* из ru (и uz)', () => {
    const ruKeys = leafKeys(ru.twa.simple).sort()
    expect(leafKeys(uzCyrl.twa.simple).sort()).toEqual(ruKeys)
    expect(leafKeys(uz.twa.simple).sort()).toEqual(ruKeys)
  })

  it('подключена в i18n: простой режим — кириллицей, остальное — фолбэк uz → ru', async () => {
    await i18n.changeLanguage(UZ_CYRL)
    expect(i18n.t('twa.simple.task.done')).toBe('Тайёр')
    expect(i18n.t('twa.exec.shift.title')).toBe(uz.twa.exec.shift.title)
    expect(document.documentElement.lang).toBe('uz-Cyrl')
  })

  it('форматтеры не падают на uz_cyrl (Intl не принимает подчёркивание)', async () => {
    await i18n.changeLanguage(UZ_CYRL)
    expect(formatNumber(1234)).toBeTruthy()
    expect(formatDate('2026-09-26T10:00:00Z')).toBeTruthy()
    expect(toBcp47('ru')).toBe('ru')
  })
})
