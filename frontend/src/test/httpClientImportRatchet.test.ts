import { describe, expect, it } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'

// A9-P3-21 — ратчет прямых HTTP-вызовов из UI-слоя дашборда.
//
// Компоненты и страницы, дёргающие `apiClient` мимо query-хуков, собирают
// ключи кэша руками и расходятся с хуками того же эндпоинта: мутация
// инвалидирует один ключ, экран читает другой — и карточка «не обновляется»
// (класс AUD8 all-apartments). Транспорт живёт в `src/hooks/**` (query/mutation
// хуки с общими фабриками ключей) и `src/api/**` (разовые императивные вызовы
// без кэша); `components/` и `pages/` импортируют уже их.
//
// Гейт сканирует `src/components/**` и `src/pages/**` (без тестов) и находит
// именованный импорт HTTP-клиента из `api/client|accessClient|publicClient`:
//   * файл импортирует клиент и его НЕТ в BASELINE — регресс: вынесите вызов в
//     хук (`src/hooks/`) или функцию API-слоя (`src/api/`), baseline вверх не
//     двигается никогда;
//   * файл из BASELINE клиент больше не импортирует — прогресс: уберите строку.
// TWA (`src/twa/**`) — отдельный auth-контур со своим twaClient, вне гейта.

const SRC = path.resolve(__dirname, '..')
const SCANNED_DIRS = ['components', 'pages']
const HTTP_CLIENTS = new Set(['apiClient', 'accessClient', 'publicClient'])
const CLIENT_MODULE = /(^|\/)api\/(client|accessClient|publicClient)$/

// Снимок 2026-10-01 после выноса A9-P3-21: прямых `apiClient` в UI-слое — 0
// файлов (было 13). Единственное исключение — вход: publicClient без
// 401-интерцептора (FE-047), сессии ещё нет, кэшировать нечего.
const BASELINE: ReadonlySet<string> = new Set(['pages/LoginPage.tsx'])

/** Имена HTTP-клиентов, импортированных значением (не `import type`). */
function importedHttpClients(source: string): string[] {
  const found: string[] = []
  const re = /import\s+(type\s+)?\{([^}]*)\}\s*from\s*['"]([^'"]+)['"]/g
  let m: RegExpExecArray | null
  while ((m = re.exec(source)) !== null) {
    const [, typeOnly, names, from] = m
    if (typeOnly || !CLIENT_MODULE.test(from)) continue
    for (const raw of names.split(',')) {
      const spec = raw.trim()
      if (!spec || spec.startsWith('type ')) continue
      const name = spec.split(/\s+as\s+/)[0].trim()
      if (HTTP_CLIENTS.has(name)) found.push(name)
    }
  }
  return found
}

function walk(dir: string): string[] {
  if (!fs.existsSync(dir)) return []
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((e) => {
    const p = path.join(dir, e.name)
    if (e.isDirectory()) return e.name === '__tests__' ? [] : walk(p)
    return /\.(ts|tsx)$/.test(e.name) && !/\.test\./.test(e.name) ? [p] : []
  })
}

function filesImportingHttpClient(): string[] {
  return SCANNED_DIRS.flatMap((d) => walk(path.join(SRC, d)))
    .filter((f) => importedHttpClients(fs.readFileSync(f, 'utf8')).length > 0)
    .map((f) => path.relative(SRC, f).split(path.sep).join('/'))
    .sort()
}

describe('importedHttpClients (детектор)', () => {
  it('видит именованный импорт, в т.ч. многострочный и с алиасом', () => {
    expect(importedHttpClients("import { apiClient } from '../../api/client'")).toEqual(['apiClient'])
    expect(importedHttpClients("import {\n  publicClient as pc,\n} from '@/api/client'")).toEqual(['publicClient'])
    expect(importedHttpClients("import { accessClient } from '../api/accessClient'")).toEqual(['accessClient'])
  })

  it('не считает type-импорты, чужие модули и упоминания в комментариях', () => {
    expect(importedHttpClients("import type { apiClient } from '../api/client'")).toEqual([])
    expect(importedHttpClients("import { type apiClient } from '../api/client'")).toEqual([])
    expect(importedHttpClients("import { fetchFileAsDataUrl } from '../api/fileDataUrl'")).toEqual([])
    expect(importedHttpClients('// байты грузятся через apiClient')).toEqual([])
  })
})

describe('A9-P3-21: HTTP-клиент в components/ и pages/ (ратчет)', () => {
  const actual = filesImportingHttpClient()

  it('новых файлов с прямым импортом HTTP-клиента нет', () => {
    expect(actual.filter((f) => !BASELINE.has(f))).toEqual([])
  })

  it('baseline не устарел — снимите строку, если файл больше не импортирует клиент', () => {
    expect([...BASELINE].filter((f) => !actual.includes(f))).toEqual([])
  })
})
