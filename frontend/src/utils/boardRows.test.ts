import { describe, it, expect } from 'vitest'
import { groupBoardRows } from './boardRows'

const F = (id: string) => ({ id, width: 'full' as const })
const H = (id: string) => ({ id, width: 'half' as const })

describe('groupBoardRows', () => {
  it('pairs two adjacent half blocks into one row', () => {
    const rows = groupBoardRows([F('stats'), H('rating'), H('hours')])
    expect(rows.map(r => r.map(i => i.id))).toEqual([['stats'], ['rating', 'hours']])
  })

  it('renders a lone half (no half neighbour) full-width', () => {
    const rows = groupBoardRows([H('rating'), F('requests')])
    expect(rows.map(r => r.map(i => i.id))).toEqual([['rating'], ['requests']])
  })

  it('pairs only consecutive halves, greedily two at a time', () => {
    const rows = groupBoardRows([H('a'), H('b'), H('c')])
    // a+b pair, c is left alone (full-width row)
    expect(rows.map(r => r.map(i => i.id))).toEqual([['a', 'b'], ['c']])
  })

  it('does not pair a half separated from another half by a full', () => {
    const rows = groupBoardRows([H('a'), F('x'), H('b')])
    expect(rows.map(r => r.map(i => i.id))).toEqual([['a'], ['x'], ['b']])
  })

  it('treats missing width as full', () => {
    const rows = groupBoardRows([{ id: 'a' }, { id: 'b' }])
    expect(rows.map(r => r.map(i => i.id))).toEqual([['a'], ['b']])
  })

  it('returns [] for empty input', () => {
    expect(groupBoardRows([])).toEqual([])
  })
})
