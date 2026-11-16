/**
 * Черновик плана уборки дома: чистые преобразования между формой и API.
 *
 * Сервер проверяет план сам (services/cleaning/planning.py) — здесь та же
 * проверка нужна, чтобы подсветить ошибку до сохранения и показать покрытие
 * этажей и предпросмотр недели по несохранённому черновику.
 */
import type { CleaningPlanItem, CleaningWorkKind } from '../../types/cleaning'

export const WEEKDAYS = [0, 1, 2, 3, 4, 5, 6] as const
/** Работы по этажам; у остальных (лифт, −1 этаж, выход на парковку) этажи не выбираются. */
export const FLOOR_WORKS: readonly CleaningWorkKind[] = ['wet', 'dry']
export const WORK_KINDS: readonly CleaningWorkKind[] = ['wet', 'dry', 'elevator', 'basement', 'parking']

export type FloorsMode = 'all' | 'first' | 'range'

export interface DraftItem {
  work_kind: CleaningWorkKind
  weekdays: number[]
  /** '' — все подъезды; иначе номера через запятую. */
  entrances: string
  floors: FloorsMode
  floor_from: string
  floor_to: string
}

export const emptyItem = (): DraftItem => ({
  work_kind: 'wet', weekdays: [], entrances: '', floors: 'all', floor_from: '', floor_to: '',
})

export function toggleDay(days: number[], day: number): number[] {
  return days.includes(day) ? days.filter((d) => d !== day) : [...days, day].sort((a, b) => a - b)
}

export function parseEntrances(raw: string): number[] | null | 'invalid' {
  const text = raw.trim()
  if (!text) return null
  const parts = text.split(',').map((p) => p.trim())
  if (!parts.every((p) => /^[1-9]\d?$/.test(p))) return 'invalid'
  return parts.map(Number)
}

function floorRange(item: DraftItem, floorCount: number): [number, number] | null {
  if (!FLOOR_WORKS.includes(item.work_kind)) return null
  if (item.floors === 'all') return [1, floorCount]
  if (item.floors === 'first') return [1, 1]
  return [Number(item.floor_from), Number(item.floor_to)]
}

export function toPayload(items: DraftItem[]): CleaningPlanItem[] {
  return items.map((item) => {
    const out: CleaningPlanItem = { work_kind: item.work_kind, weekdays: item.weekdays }
    if (FLOOR_WORKS.includes(item.work_kind) && item.floors !== 'all') {
      out.floor_from = item.floors === 'first' ? 1 : Number(item.floor_from)
      out.floor_to = item.floors === 'first' ? 1 : Number(item.floor_to)
    }
    const entrances = parseEntrances(item.entrances)
    if (Array.isArray(entrances)) out.entrances = entrances
    return out
  })
}

export function draftFrom(items: CleaningPlanItem[]): DraftItem[] {
  return items.map((item) => {
    const ranged = item.floor_from != null && item.floor_to != null
    const first = ranged && item.floor_from === 1 && item.floor_to === 1
    return {
      work_kind: item.work_kind,
      weekdays: [...item.weekdays],
      entrances: (item.entrances ?? []).join(', '),
      floors: !ranged ? 'all' : first ? 'first' : 'range',
      floor_from: ranged && !first ? String(item.floor_from) : '',
      floor_to: ranged && !first ? String(item.floor_to) : '',
    }
  })
}

export type PlanProblem = 'empty' | 'weekdays' | 'floors' | 'entrances'

export function validate(items: DraftItem[], floorCount: number, entranceCount: number): PlanProblem | null {
  if (items.length === 0) return 'empty'
  for (const item of items) {
    if (item.weekdays.length === 0) return 'weekdays'
    const range = floorRange(item, floorCount)
    if (range) {
      const [from, to] = range
      if (!Number.isInteger(from) || !Number.isInteger(to) || from < 1 || to > floorCount || from > to) return 'floors'
    }
    const entrances = parseEntrances(item.entrances)
    if (entrances === 'invalid' || (entrances && entrances.some((e) => e > entranceCount))) return 'entrances'
  }
  return null
}

/** Одна работа по всем этажам → две строки: нижняя и верхняя половина через день. */
export function splitInHalf(item: DraftItem, floorCount: number): [DraftItem, DraftItem] {
  const middle = Math.ceil(floorCount / 2)
  const low = item.weekdays.filter((_, i) => i % 2 === 0)
  const high = item.weekdays.filter((_, i) => i % 2 === 1)
  const half = (from: number, to: number, weekdays: number[]): DraftItem => ({
    ...item, floors: 'range', floor_from: String(from), floor_to: String(to), weekdays,
  })
  return [half(1, middle, low), half(middle + 1, floorCount, high)]
}

/** Сколько раз в неделю работа проходит по этажу (индекс 0 — первый этаж). */
export function coverage(items: DraftItem[], kind: CleaningWorkKind, floorCount: number, entranceCount = 1): number[] {
  // По худшему подъезду: строка «только подъезд 1» не закрывает этажи подъезда 2.
  const worst = Array<number>(floorCount).fill(Infinity)
  for (let entrance = 1; entrance <= Math.max(1, entranceCount); entrance += 1) {
    const counts = Array<number>(floorCount).fill(0)
    for (const item of items) {
      const range = item.work_kind === kind ? floorRange(item, floorCount) : null
      const entrances = parseEntrances(item.entrances)
      if (!range || (Array.isArray(entrances) && !entrances.includes(entrance))) continue
      for (let floor = Math.max(1, range[0]); floor <= Math.min(floorCount, range[1]); floor += 1) {
        counts[floor - 1] += item.weekdays.length
      }
    }
    counts.forEach((n, i) => { worst[i] = Math.min(worst[i], n) })
  }
  return worst
}

export interface PreviewWork {
  kind: CleaningWorkKind
  from?: number
  to?: number
}

export interface PreviewDay {
  works: PreviewWork[]
  /** Этажей к съёмке в одном подъезде. */
  floors: number
}

export function weekPreview(items: DraftItem[], floorCount: number): PreviewDay[] {
  return WEEKDAYS.map((day) => {
    const todays = items.filter((item) => item.weekdays.includes(day))
    const floors = new Set<number>()
    const works = todays.map((item): PreviewWork => {
      const range = floorRange(item, floorCount)
      if (!range) return { kind: item.work_kind }
      for (let floor = range[0]; floor <= range[1]; floor += 1) floors.add(floor)
      return { kind: item.work_kind, from: range[0], to: range[1] }
    })
    return { works, floors: floors.size }
  })
}
