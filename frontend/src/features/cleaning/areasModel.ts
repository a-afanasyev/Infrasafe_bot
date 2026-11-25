import type { CleaningAreas, CleaningEntranceAreas } from '../../types/cleaning'

/**
 * Площади мест общего пользования дома (м²) для нагрузки уборщиц: черновик формы ↔ JSON API.
 * Строка «*» — все подъезды; строка подъезда переопределяет только заполненные поля.
 * 1-й и −1 этажи — отдельные поля, остальные отличающиеся этажи — текстом «16:31; 30:28.5».
 */
export const ALL_ENTRANCES = '*'
export const POINT_KINDS = ['elevator', 'parking', 'fire_stairs'] as const
export type PointKind = (typeof POINT_KINDS)[number]
const MAX_M2 = 10000

export interface AreasDraftRow {
  scope: string
  typical: string
  floor1: string
  basement: string
  special: string
  points: Record<PointKind, string>
}

export type AreasError = 'badNumber' | 'badSpecial'

export function emptyRow(scope: string): AreasDraftRow {
  return { scope, typical: '', floor1: '', basement: '', special: '', points: { elevator: '', parking: '', fire_stairs: '' } }
}

const str = (value: number | undefined) => (value == null ? '' : String(value))

function rowFrom(scope: string, own: CleaningEntranceAreas): AreasDraftRow {
  const { '1': floor1, '-1': basement, ...rest } = own.floors ?? {}
  const special = Object.entries(rest)
    .sort(([a], [b]) => Number(a) - Number(b))
    .map(([floor, m2]) => `${floor}:${m2}`)
    .join('; ')
  const points = { ...emptyRow(scope).points }
  for (const kind of POINT_KINDS) points[kind] = str(own.points?.[kind])
  return { scope, typical: str(own.typical), floor1: str(floor1), basement: str(basement), special, points }
}

export function draftFromAreas(areas: CleaningAreas | null): AreasDraftRow[] {
  const entrances = areas?.entrances ?? {}
  const own = Object.keys(entrances).filter((key) => key !== ALL_ENTRANCES).sort((a, b) => Number(a) - Number(b))
  return [rowFrom(ALL_ENTRANCES, entrances[ALL_ENTRANCES] ?? {}), ...own.map((key) => rowFrom(key, entrances[key]))]
}

class DraftError extends Error {
  readonly code: AreasError
  constructor(code: AreasError) {
    super(code)
    this.code = code
  }
}

function m2(text: string, code: AreasError = 'badNumber'): number | undefined {
  const trimmed = text.trim().replace(',', '.')
  if (trimmed === '') return undefined
  const value = Number(trimmed)
  if (!Number.isFinite(value) || value < 0 || value > MAX_M2) throw new DraftError(code)
  return value
}

function specialFloors(text: string): Record<string, number> {
  const out: Record<string, number> = {}
  for (const part of text.split(';').map((p) => p.trim()).filter(Boolean)) {
    const match = /^(-?\d+)\s*:\s*(.+)$/.exec(part)
    if (!match || Number(match[1]) === 0) throw new DraftError('badSpecial')
    out[String(Number(match[1]))] = m2(match[2], 'badSpecial') as number
  }
  return out
}

function entranceFrom(row: AreasDraftRow): CleaningEntranceAreas | null {
  const floors: Record<string, number> = specialFloors(row.special)
  const floor1 = m2(row.floor1)
  const basement = m2(row.basement)
  if (floor1 !== undefined) floors['1'] = floor1
  if (basement !== undefined) floors['-1'] = basement
  const points: Partial<Record<PointKind, number>> = {}
  for (const kind of POINT_KINDS) {
    const value = m2(row.points[kind])
    if (value !== undefined) points[kind] = value
  }
  const typical = m2(row.typical)
  const out: CleaningEntranceAreas = {
    ...(typical !== undefined && { typical }),
    ...(Object.keys(floors).length > 0 && { floors }),
    ...(Object.keys(points).length > 0 && { points }),
  }
  return Object.keys(out).length > 0 ? out : null
}

/** Черновик → тело PUT; все поля пустые — `null` (площади убрать). */
export function areasFromDraft(rows: AreasDraftRow[]): { areas: CleaningAreas | null } | { error: AreasError } {
  try {
    const entrances: Record<string, CleaningEntranceAreas> = {}
    for (const row of rows) {
      const own = entranceFrom(row)
      if (own) entrances[row.scope] = own
    }
    return { areas: Object.keys(entrances).length > 0 ? { entrances } : null }
  } catch (err) {
    if (err instanceof DraftError) return { error: err.code }
    throw err
  }
}
