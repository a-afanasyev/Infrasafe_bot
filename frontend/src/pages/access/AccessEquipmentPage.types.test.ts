import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

// AUD8-FE-04: payload'ы форм оборудования типизированы по конкретному
// Create*Payload (FormField<T>.name = keyof T) — приведение `as never` обходило
// проверку и превращало опечатку в имени поля в 422 на проде.
describe('AccessEquipmentPage: типизация payload', () => {
  it('в странице нет `as never`, а каждая схема формы типизирована', () => {
    const src = readFileSync(join(__dirname, 'AccessEquipmentPage.tsx'), 'utf8')
    expect(src).not.toMatch(/as never/)
    expect(src).not.toMatch(/FormField\[\]/)
    expect(src.match(/FormField<Create\w+Payload>\[\]/g)?.length).toBe(5)
  })
})
