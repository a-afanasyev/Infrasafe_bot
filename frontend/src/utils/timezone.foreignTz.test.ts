import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest'

import {
  DEFAULT_DISPLAY_TZ,
  datetimeLocalToIso,
  fromDisplayTz,
  isoToDatetimeLocal,
  nowInDisplayTz,
  setDisplayTz,
  todayInDisplayTz,
} from './timezone'
import { startOfDay, startOfWeek } from './shiftWeek'

// ARCH-137 B7: дефект «календарь считается в зоне браузера» невидим, когда
// раннер живёт в display-зоне (локально Ташкент) или в UTC (CI даёт лишь
// частичный контраст). Этот файл прогоняет календарную математику с раннером
// в America/New_York (UTC-4 летом) — контраст с Ташкентом 9 часов, границы
// суток расходятся на бо́льшую часть дня.
//
// Node пере-читает process.env.TZ на лету (ICU) — guard-тест ниже проверяет,
// что подмена реально применилась, иначе весь файл — ложно-зелёный.

const ORIG_TZ = process.env.TZ

beforeAll(() => {
  process.env.TZ = 'America/New_York'
})

afterAll(() => {
  if (ORIG_TZ === undefined) delete process.env.TZ
  else process.env.TZ = ORIG_TZ
})

afterEach(() => {
  vi.useRealTimers()
  setDisplayTz(DEFAULT_DISPLAY_TZ)
})

it('guard: раннер действительно в America/New_York', () => {
  // Август: EDT = UTC-4 → offset 240 минут.
  expect(new Date('2026-08-01T12:00:00Z').getTimezoneOffset()).toBe(240)
})

describe('«в браузере ещё 1 августа, в зоне объекта уже 2-е»', () => {
  it('nowInDisplayTz даёт день объекта, а не браузера', () => {
    // 01:00Z 2 августа = 21:00 1 августа в Нью-Йорке, 06:00 2 августа в Ташкенте.
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-08-02T01:00:00Z'))
    expect(new Date().getDate()).toBe(1) // браузер ещё «вчера»
    const today = nowInDisplayTz()
    expect([today.getFullYear(), today.getMonth(), today.getDate()]).toEqual([2026, 7, 2])
    // date-only вариант (дефолт даты в шаблонной модалке) — тоже день объекта,
    // а не UTC- и не браузерный день.
    expect(todayInDisplayTz()).toBe('2026-08-02')
  })

  it('дневное окно строится по границам дня объекта', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-08-02T01:00:00Z'))
    const dayStart = startOfDay(nowInDisplayTz())
    // Полночь 2 августа в Ташкенте = 19:00Z 1 августа.
    expect(fromDisplayTz(dayStart)).toBe('2026-08-01T19:00:00.000Z')
  })

  it('граница недели — понедельник по календарю объекта', () => {
    // 2026-08-02 — воскресенье; понедельник его ISO-недели — 27 июля.
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-08-02T01:00:00Z'))
    const wkStart = startOfWeek(nowInDisplayTz())
    expect(fromDisplayTz(wkStart)).toBe('2026-07-26T19:00:00.000Z')
  })
})

describe('round-trip ввода не зависит от зоны браузера', () => {
  it('fromDisplayTz(isoToDatetimeLocal(x)) == x при раннере в Нью-Йорке', () => {
    for (const iso of [
      '2026-08-04T20:30:00.000Z',
      '2026-08-04T04:00:00.000Z', // 09:00 Ташкента = ещё вчера в Нью-Йорке
      '2026-01-15T19:00:00.000Z', // зима: NY в EST (UTC-5)
    ]) {
      expect(fromDisplayTz(isoToDatetimeLocal(iso))).toBe(iso)
    }
  })

  it('datetime-local «09:00» уезжает на сервер как 09:00 объекта, не браузера', () => {
    // Менеджер из Нью-Йорка ставит смену на 09:00 — это 04:00Z (Ташкент),
    // а НЕ 13:00Z (нью-йоркская трактовка new Date(...).toISOString()).
    expect(fromDisplayTz('2026-08-04T09:00')).toBe('2026-08-04T04:00:00.000Z')
  })

  it('datetimeLocalToIso (ARCH-138, «действителен до» в access): зона объекта + деградация', () => {
    expect(datetimeLocalToIso('2026-08-04T09:00')).toBe('2026-08-04T04:00:00.000Z')
    expect(datetimeLocalToIso('')).toBeUndefined()
    expect(datetimeLocalToIso('   ')).toBeUndefined()
    expect(datetimeLocalToIso('not-a-date')).toBeUndefined()
  })
})
