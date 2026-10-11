import { describe, it, expect } from 'vitest'
import { testI18n } from '../../test/test-utils'
import type { PlannedWorkCfg, WorkingHourCfg } from '../../types/boardConfig'
import { DEFAULT_DISPLAY_TZ, setDisplayTz } from '../../utils/timezone'
import {
  announcementWall,
  botHandle,
  categoryLine,
  formatWorkingHours,
  telHref,
  upcomingWorks,
  wallDateTimeLabel,
  workDateLabel,
  workDateParts,
} from './homeFormat'

const t = testI18n.getFixedT('ru')
const tUz = testI18n.getFixedT('uz')

function hours(overrides: Partial<Record<string, Partial<WorkingHourCfg>>> = {}): WorkingHourCfg[] {
  return ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'].map((day) => ({
    day,
    open: '09:00',
    close: '18:00',
    closed: false,
    ...overrides[day],
  }))
}

function work(id: string, date: string, time_from = '', time_to = ''): PlannedWorkCfg {
  return {
    id, date, time_from, time_to,
    title: { ru: id, uz: id }, place: { ru: '', uz: '' }, text: { ru: '', uz: '' },
  }
}

describe('formatWorkingHours', () => {
  it('сворачивает подряд идущие дни с одинаковым графиком', () => {
    const line = formatWorkingHours(
      hours({ sat: { open: '09:00', close: '17:00' }, sun: { closed: true } }),
      t,
    )
    expect(line).toBe('Пн–Пт 09:00–18:00 · Сб 09:00–17:00 · Вс выходной')
  })

  it('одинаковый график всю неделю — одна группа', () => {
    expect(formatWorkingHours(hours(), t)).toBe('Пн–Вс 09:00–18:00')
  })

  it('не склеивает несмежные дни с одинаковым графиком', () => {
    const line = formatWorkingHours(hours({ wed: { closed: true } }), t)
    expect(line).toBe('Пн–Вт 09:00–18:00 · Ср выходной · Чт–Вс 09:00–18:00')
  })
})

describe('upcomingWorks', () => {
  it('сегодня и позже, по дате и времени, с лимитом', () => {
    const list = upcomingWorks(
      [work('past', '2026-10-10'), work('late', '2026-10-15', '14:00'),
        work('early', '2026-10-15', '09:00'), work('today', '2026-10-11'), work('far', '2026-12-01')],
      '2026-10-11',
      3,
    )
    expect(list.map((w) => w.id)).toEqual(['today', 'early', 'late'])
  })

  it('не мутирует входной список', () => {
    const input = [work('b', '2026-10-20'), work('a', '2026-10-12')]
    upcomingWorks(input, '2026-10-11', 5)
    expect(input.map((w) => w.id)).toEqual(['b', 'a'])
  })
})

describe('даты работ', () => {
  it('плитка: день без ведущего нуля и короткий месяц', () => {
    expect(workDateParts('2026-10-05', t)).toEqual({ day: '5', month: 'окт' })
  })

  it('подпись: дата и интервал, без времени — только дата', () => {
    expect(workDateLabel(work('w', '2026-10-15', '10:00', '12:00'), t, 'ru')).toBe('15 октября · 10:00–12:00')
    expect(workDateLabel(work('w', '2026-10-15'), t, 'ru')).toBe('15 октября')
    expect(workDateLabel(work('w', '2026-10-15', '10:00', '12:00'), tUz, 'uz')).toBe('15-oktabr · 10:00–12:00')
  })

  it('стенка объявления', () => {
    expect(wallDateTimeLabel(new Date(2026, 9, 15, 9, 5), t, 'ru')).toBe('15 октября · 09:05')
  })
})

describe('announcementWall', () => {
  it('naive-строка редактора — уже стенка объекта, зона браузера не участвует', () => {
    const wall = announcementWall('2026-10-15T09:30')
    expect(wall && [wall.getDate(), wall.getHours(), wall.getMinutes()]).toEqual([15, 9, 30])
  })

  it('значение с зоной — инстант в display-зону', () => {
    setDisplayTz('Asia/Tashkent')
    const wall = announcementWall('2026-10-15T04:30:00Z')
    expect(wall && [wall.getDate(), wall.getHours()]).toEqual([15, 9])
    setDisplayTz(DEFAULT_DISPLAY_TZ)
  })

  it('мусор → null', () => {
    expect(announcementWall('')).toBeNull()
    expect(announcementWall('вчера')).toBeNull()
  })
})

describe('categoryLine', () => {
  it('по убыванию, переведённые категории, не больше лимита', () => {
    const line = categoryLine({ plumbing: 3, 'Электрика': 5, cleaning: 0, heating: 1 }, t, 2)
    expect(line).toBe('Электрика — 5 · Сантехника — 3')
  })

  it('пусто → пустая строка', () => {
    expect(categoryLine(undefined, t)).toBe('')
  })
})

describe('ссылки', () => {
  it('tel: без пробелов и дефисов', () => {
    expect(telHref('+998 78 333-19-71')).toBe('tel:+998783331971')
  })

  it('username бота без @ и посторонних символов', () => {
    expect(botHandle('@profk_bot/../x')).toBe('profk_botx')
  })
})
