import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { getUrgencyStyle } from './urgencyStyle'

// A9-P3-20: один канон цветов срочности для карточки и модалки заявки.
describe('getUrgencyStyle', () => {
  it('канон-ключ и legacy-рус дают один и тот же стиль', () => {
    expect(getUrgencyStyle('medium')).toEqual(getUrgencyStyle('Средняя'))
    expect(getUrgencyStyle('critical')).toEqual({ bg: 'bg-red/12', text: 'text-red' })
  })

  it('неизвестный/пустой ключ → null', () => {
    expect(getUrgencyStyle('')).toBeNull()
    expect(getUrgencyStyle(null)).toBeNull()
    expect(getUrgencyStyle('nope')).toBeNull()
  })

  it('локальных копий таблицы срочности в карточке и модалке больше нет', () => {
    for (const file of ['RequestCard.tsx', 'RequestDetailModal.tsx']) {
      const src = readFileSync(resolve(__dirname, file), 'utf-8')
      expect(src).not.toMatch(/const URGENCY\b/)
      expect(src).toContain('getUrgencyStyle')
    }
  })
})
