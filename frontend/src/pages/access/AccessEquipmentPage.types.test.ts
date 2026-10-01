import { describe, it, expect } from 'vitest'
import { readdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'

// AUD8-FE-04: payload'ы форм оборудования типизированы по конкретному
// Create*Payload (FormField<T>.name = keyof T) — приведение `as never` обходило
// проверку и превращало опечатку в имени поля в 422 на проде.
// A9-P3-21: панели табов вынесены в components/access/equipment/ — гейт
// сканирует страницу и все панели вместе.
const EQUIPMENT_DIR = join(__dirname, '..', '..', 'components', 'access', 'equipment')

function equipmentSources(): string[] {
  const panels = readdirSync(EQUIPMENT_DIR)
    .filter((f) => /\.tsx?$/.test(f) && !/\.test\./.test(f))
    .map((f) => join(EQUIPMENT_DIR, f))
  return [join(__dirname, 'AccessEquipmentPage.tsx'), ...panels].map((p) => readFileSync(p, 'utf8'))
}

describe('AccessEquipmentPage: типизация payload', () => {
  it('в странице и панелях нет `as never`, а каждая схема формы типизирована', () => {
    const src = equipmentSources().join('\n')
    expect(src).not.toMatch(/as never/)
    expect(src).not.toMatch(/FormField\[\]/)
    expect(src.match(/FormField<Create\w+Payload>\[\]/g)?.length).toBe(5)
  })
})
