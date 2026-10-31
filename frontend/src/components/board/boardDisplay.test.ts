import { describe, expect, it } from 'vitest'
import { boardClock, boardDay, boardPublished, groupBoardHours, splitBoardText } from './boardDisplay'

describe('board display', () => {
  it('groups only consecutive days with matching configured hours', () => {
    const days = ['mon', 'tue', 'wed', 'fri', 'sat']
    const hours = days.map(day => ({ day, open: '09:00', close: day === 'sat' ? '17:00' : '18:00', closed: false }))
    expect(groupBoardHours(hours).map(group => group.days)).toEqual([['mon', 'tue', 'wed'], ['fri'], ['sat']])
  })
  it('uses the object timezone across midnight, independent of the browser', () => {
    const date = new Date('2026-10-11T20:10:30Z')
    expect(boardClock(date, 'Asia/Tashkent')).toBe('01:10')
    expect(boardClock(date, 'Asia/Tashkent', true)).toBe('01:10:30')
    expect(boardDay(date, 'Asia/Tashkent')).toBe('mon')
    expect(boardDay(date, 'America/Los_Angeles')).toBe('sun')
  })
  it('interprets editor dates in the object timezone and ISO dates as instants', () => {
    expect(boardPublished('2026-10-12T01:10', 'Asia/Tashkent')).toBe('12.10, 01:10')
    expect(boardPublished('2026-10-11T20:10:00Z', 'Asia/Tashkent')).toBe('12.10, 01:10')
    expect(boardPublished('invalid', 'Asia/Tashkent')).toBe('')
  })
  it('does not split emoji surrogate pairs between slides', () => {
    expect(splitBoardText('📢'.repeat(65), 30)).toEqual(['📢'.repeat(30), '📢'.repeat(30), '📢'.repeat(5)])
  })
  it('paginates all text, including a word longer than a slide', () => {
    const text = 'Объявление '.repeat(60) + 'А'.repeat(350)
    const pages = splitBoardText(text, 140)
    expect(pages.length).toBeGreaterThan(1)
    expect(pages.every(page => page.length <= 140)).toBe(true)
    expect(pages.join('').replace(/\s/g, '')).toBe(text.replace(/\s/g, ''))
  })
})
