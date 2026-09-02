import { describe, expect, it } from 'vitest'

import {
  NAME_CASE_DEFAULT,
  formatPersonName,
  isNameCase,
  joinPersonName,
} from './nameCase'

// Предпочтение менеджера «ФИО заглавными буквами»: единый форматтер для всех
// точек рендера имён в дашборде. Fallback'и (`#12`, «Без имени») форматтер
// не знает — их подставляет вызывающий код после `|| fallback`.

describe('formatPersonName — title (КАПС → Вид Имени)', () => {
  it('капс-слова приводятся, узбекский апостроф не капитализируется', () => {
    expect(formatPersonName('ABDULLAXATOV AZIZJON ABDUAKIM O’G’LI', 'title'))
      .toBe('Abdullaxatov Azizjon Abduakim O’g’li')
    expect(formatPersonName('KALMENOVA NAGIMA QUCHQOR QIZI', 'title'))
      .toBe('Kalmenova Nagima Quchqor Qizi')
    expect(formatPersonName("O'KTAMOV ANNA-MARIA", 'title')).toBe("O'ktamov Anna-Maria")
  })

  it('уже нормальный регистр не трогаем', () => {
    expect(formatPersonName('Mirzabek Valiulin', 'title')).toBe('Mirzabek Valiulin')
    expect(formatPersonName('МакКей де Соуза', 'title')).toBe('МакКей де Соуза')
  })

  it('кириллический капс приводится', () => {
    expect(formatPersonName('ИВАНОВ ИВАН ИВАНОВИЧ', 'title')).toBe('Иванов Иван Иванович')
  })

  it('не-буквенные строки инвариантны', () => {
    expect(formatPersonName('#12', 'title')).toBe('#12')
    expect(formatPersonName('—', 'title')).toBe('—')
  })
})

describe('formatPersonName — caps', () => {
  it('переводит всё в верхний регистр, включая апостроф-буквы', () => {
    expect(formatPersonName("O'ktamov Anna-Maria", 'caps')).toBe("O'KTAMOV ANNA-MARIA")
    expect(formatPersonName('Иванов Иван', 'caps')).toBe('ИВАНОВ ИВАН')
  })

  it('капс остаётся капсом', () => {
    expect(formatPersonName('KASIMOV TALGAT', 'caps')).toBe('KASIMOV TALGAT')
  })
})

describe('formatPersonName — пустой ввод и пробелы', () => {
  it.each(['title', 'caps'] as const)('null/undefined/пробелы → "" (%s)', mode => {
    expect(formatPersonName(null, mode)).toBe('')
    expect(formatPersonName(undefined, mode)).toBe('')
    expect(formatPersonName('   ', mode)).toBe('')
  })

  it('схлопывает повторные пробелы и обрезает края', () => {
    expect(formatPersonName('  Иван   Петров ', 'title')).toBe('Иван Петров')
    expect(formatPersonName('  Иван   Петров ', 'caps')).toBe('ИВАН ПЕТРОВ')
  })
})

describe('joinPersonName', () => {
  it('склеивает first + last через пробел', () => {
    expect(joinPersonName('Иван', 'Петров')).toBe('Иван Петров')
  })
  it('пустые части отбрасывает', () => {
    expect(joinPersonName('Иван', null)).toBe('Иван')
    expect(joinPersonName(undefined, 'Петров')).toBe('Петров')
    expect(joinPersonName('', '  ')).toBe('')
    expect(joinPersonName(null, null)).toBe('')
  })
})

describe('isNameCase / NAME_CASE_DEFAULT', () => {
  it('принимает только известные режимы', () => {
    expect(isNameCase('title')).toBe(true)
    expect(isNameCase('caps')).toBe(true)
    expect(isNameCase('upper')).toBe(false)
    expect(isNameCase(null)).toBe(false)
  })
  it('дефолт — title', () => {
    expect(NAME_CASE_DEFAULT).toBe('title')
  })
})
