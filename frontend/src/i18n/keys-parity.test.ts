import { describe, it, expect } from 'vitest'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'
import ru from './locales/ru.json'
import uz from './locales/uz.json'

// AUD8-FE-02: гейт — каждый статический ключ t('…') из исходников есть в ru и uz.
// Динамические ключи (шаблонные строки, переменные) не проверяются.

const SRC = join(__dirname, '..')
const KEY_RE = /\bt\(\s*'([a-zA-Z0-9_.-]+)'/g

function walk(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name)
    if (statSync(p).isDirectory()) {
      if (name === 'node_modules' || name === 'i18n') continue
      walk(p, out)
    } else if (/\.(ts|tsx)$/.test(name) && !/\.test\.tsx?$/.test(name)) {
      out.push(p)
    }
  }
  return out
}

function lookup(obj: unknown, key: string): unknown {
  return key.split('.').reduce<unknown>((o, k) => (o && typeof o === 'object' ? (o as Record<string, unknown>)[k] : undefined), obj)
}

// Плюральные ключи i18next хранятся как key_one/_few/_many/_other (uz — только _other).
const PLURAL_SUFFIXES = ['', '_one', '_few', '_many', '_other', '_zero']

function has(obj: unknown, key: string): boolean {
  return PLURAL_SUFFIXES.some((suffix) => lookup(obj, key + suffix) !== undefined)
}

describe('i18n: статические ключи есть в обеих локалях', () => {
  it('ru и uz содержат все t(\'…\') из исходников', () => {
    const missing: string[] = []
    for (const file of walk(SRC)) {
      const src = readFileSync(file, 'utf8')
      for (const m of src.matchAll(KEY_RE)) {
        const key = m[1]
        for (const [name, dict] of [['ru', ru], ['uz', uz]] as const) {
          if (!has(dict, key)) missing.push(`${name}: ${key} (${file.replace(SRC, 'src')})`)
        }
      }
    }
    expect(missing).toEqual([])
  })
})
