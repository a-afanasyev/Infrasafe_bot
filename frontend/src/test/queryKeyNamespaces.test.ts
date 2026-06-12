import { describe, expect, it } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'

// FE-03 (PR-4): TWA-поддерево (Bearer twaClient) и dashboard (cookie apiClient)
// живут в одном QueryClient у части пользователей — пересечение queryKey
// означает перекрёстный кэш между разными auth-контурами. Этот тест статически
// сканирует исходники и гарантирует дизъюнктность: все TWA-ключи начинаются
// с 'twa', dashboard ключей 'twa' не использует.

const SRC = path.resolve(__dirname, '..')
const TWA_DIRS = [path.join(SRC, 'twa'), path.join(SRC, 'pages', 'twa')]

function walk(dir: string): string[] {
  if (!fs.existsSync(dir)) return []
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap(e => {
    const p = path.join(dir, e.name)
    if (e.isDirectory()) return walk(p)
    return /\.(ts|tsx)$/.test(e.name) && !/\.test\./.test(e.name) ? [p] : []
  })
}

function isTwaFile(file: string): boolean {
  return TWA_DIRS.some(d => file.startsWith(d + path.sep))
}

/** Первые строковые литералы query-key массивов: queryKey:/setQueryData(/removeQueries({queryKey: [...]. */
function extractKeyHeads(source: string): string[] {
  const heads: string[] = []
  const re = /(?:queryKey:\s*|setQueryData\(\s*)\[\s*'([^']+)'/g
  let m: RegExpExecArray | null
  while ((m = re.exec(source)) !== null) heads.push(m[1])
  return heads
}

describe('queryKey namespaces (FE-03)', () => {
  const files = walk(SRC)
  const twaHeads = new Set<string>()
  const dashboardHeads = new Set<string>()
  for (const f of files) {
    const heads = extractKeyHeads(fs.readFileSync(f, 'utf8'))
    for (const h of heads) (isTwaFile(f) ? twaHeads : dashboardHeads).add(h)
  }

  it('finds query keys on both sides (sanity)', () => {
    expect(twaHeads.size).toBeGreaterThan(0)
    expect(dashboardHeads.size).toBeGreaterThan(0)
  })

  it("every TWA query key starts with 'twa'", () => {
    expect([...twaHeads].filter(h => h !== 'twa')).toEqual([])
  })

  it("dashboard never uses the 'twa' namespace", () => {
    expect(dashboardHeads.has('twa')).toBe(false)
  })
})
