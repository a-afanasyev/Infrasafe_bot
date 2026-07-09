#!/usr/bin/env node
// Brand-hardcode guard. Держит два бренда (InfraSafe/PROFK) в синхроне: в
// компонентах бренд-цвета/лого должны идти через токены (var(--accent),
// bg-accent, rgba(var(--accent-rgb),α), brand.logoMark), а не сырыми литералами
// — иначе PROFK молча разъезжается. Падает (exit 1), если находит сырой
// бренд-hex или имя лого-файла в src/**/*.{ts,tsx} вне разрешённых мест.
//
// Разрешено:
//   • token-defs в index.css (не сканируется — .css вне охвата)
//   • src/brand/brand.ts (конфиг бренда — в SKIP_FILES)
//   • *.test.ts(x) (не сканируются)
//   • любая строка с маркером `brand-allow` (категориальные палитры, палитра
//     публичного табло ResidentBoardPage)

import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative, sep } from 'node:path'
import { fileURLToPath } from 'node:url'

const SRC = fileURLToPath(new URL('../src', import.meta.url))

// Файлы, где бренд-литералы легитимны целиком.
//   • brand/brand.ts — конфиг бренда
//   • pages/ResidentBoardPage.tsx — публичное табло с собственной палитрой
//     (#1a6b52/Sora), намеренно независимой от токенов темы (см. plan §PROFK)
const SKIP_FILES = new Set([
  join('brand', 'brand.ts'),
  join('pages', 'ResidentBoardPage.tsx'),
])

const ALLOW_MARKER = 'brand-allow'

const PATTERNS = [
  /#00d4aa/i, // InfraSafe accent
  /#00f0c0/i, // InfraSafe accent-hover
  /#44c24a/i, // PROFK accent
  /#1a6b52/i, // ResidentBoard public-board palette
  /infrasafe-logo\.svg/i,
  /profk-(?:mark|logo|favicon)\.svg/i,
]

/** @param {string} dir @param {string[]} out */
function walk(dir, out) {
  for (const name of readdirSync(dir)) {
    const full = join(dir, name)
    if (statSync(full).isDirectory()) {
      walk(full, out)
    } else if (/\.tsx?$/.test(name) && !/\.test\.tsx?$/.test(name)) {
      out.push(full)
    }
  }
}

const files = []
walk(SRC, files)

const violations = []
for (const file of files) {
  const rel = relative(SRC, file)
  if (SKIP_FILES.has(rel)) continue
  const lines = readFileSync(file, 'utf8').split('\n')
  lines.forEach((line, i) => {
    if (line.includes(ALLOW_MARKER)) return
    if (PATTERNS.some((p) => p.test(line))) {
      violations.push({ path: `src${sep}${rel}`, line: i + 1, text: line.trim() })
    }
  })
}

if (violations.length) {
  console.error('✖ brand-hardcode guard: сырой бренд-цвет/лого в компонентах.')
  console.error('  Используй токены (var(--accent), bg-accent, brand.logoMark)')
  console.error('  или пометь легитимную строку комментарием `brand-allow`.\n')
  for (const v of violations) {
    console.error(`  ${v.path}:${v.line}  ${v.text}`)
  }
  process.exit(1)
}

console.log(`✓ brand-hardcode guard: чисто (${files.length} файлов).`)
