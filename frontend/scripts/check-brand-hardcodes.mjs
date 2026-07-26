#!/usr/bin/env node
// Brand-hardcode guard. Держит два бренда (InfraSafe/PROFK) в синхроне: в
// компонентах бренд-цвета/лого должны идти через токены (var(--accent),
// bg-accent, rgba(var(--accent-rgb),α), brand.logoMark), а не сырыми литералами
// — иначе PROFK молча разъезжается. Падает (exit 1), если находит сырой
// бренд-цвет или имя лого-файла вне разрешённых мест.
//
// AUD5-APIFE-18 (2026-07-26). Раньше гейт держал СПИСОК из четырёх hex прямо
// здесь, и это давало три дыры:
//   1. новый оттенок бренда список не знал — `#3aa540` (PROFK accent-hover,
//      `index.css:112`) не ловился вообще, хотя это ровно тот класс литерала,
//      от которого гейт защищает;
//   2. десятичная запись того же цвета (`rgb(0,212,170)`, `rgba(68,194,74,.2)`)
//      проходила мимо hex-паттернов;
//   3. `.css` не сканировался, поэтому мимо токенов можно было уехать в стилях.
// Теперь набор цветов ВЫВОДИТСЯ из SSOT — из объявлений `--*accent*` в
// `src/index.css` (там живут оба брендовых блока). Добавили брендовый оттенок в
// токены — гейт узнал о нём в тот же коммит, без правки этого файла.

import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative, sep } from 'node:path'
import { fileURLToPath } from 'node:url'

const SRC = fileURLToPath(new URL('../src', import.meta.url))

// SSOT токенов: оба брендовых блока (`:root` и `html[data-brand="profk"]`).
// Сам файл не сканируется — определять цвет здесь и есть его назначение.
const TOKENS_CSS = join(SRC, 'index.css')

// Файлы, где бренд-литералы легитимны целиком.
//   • brand/brand.ts — конфиг бренда
//   • pages/ResidentBoardPage.tsx — публичное табло с собственной палитрой
//     (#1a6b52/Sora), намеренно независимой от токенов темы (см. plan §PROFK)
const SKIP_FILES = new Set([
  join('brand', 'brand.ts'),
  join('pages', 'ResidentBoardPage.tsx'),
  'index.css',
])

const ALLOW_MARKER = 'brand-allow'

/** #rrggbb -> "r,g,b" */
function hexToTriple(hex) {
  const h = hex.replace('#', '')
  return [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16)).join(',')
}

/** "r,g,b" -> #rrggbb */
function tripleToHex(triple) {
  return (
    '#' +
    triple
      .split(',')
      .map((n) => Number(n.trim()).toString(16).padStart(2, '0'))
      .join('')
  )
}

/**
 * Брендовые цвета из объявлений `--*accent*` в index.css, в обеих записях.
 * Возвращает Set строк вида "#00d4aa" и "0,212,170".
 */
function brandColorsFromTokens() {
  const css = readFileSync(TOKENS_CSS, 'utf8')
  const hexes = new Set()
  const triples = new Set()

  for (const line of css.split('\n')) {
    if (!/^\s*--[\w-]*accent[\w-]*\s*:/.test(line)) continue
    for (const m of line.matchAll(/#([0-9a-fA-F]{6})\b/g)) {
      hexes.add(`#${m[1].toLowerCase()}`)
    }
    // `--accent-rgb: 0,212,170` и `rgba(68,194,74,0.12)` — тот же цвет каналами.
    for (const m of line.matchAll(/(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})/g)) {
      triples.add(`${Number(m[1])},${Number(m[2])},${Number(m[3])}`)
    }
  }

  // Обе записи одного цвета взаимно дополняются: hex, объявленный только как
  // `--accent`, тоже должен ловиться в rgb()-форме, и наоборот.
  for (const h of [...hexes]) triples.add(hexToTriple(h))
  for (const t of [...triples]) hexes.add(tripleToHex(t))

  // Ахроматические значения (r==g==b: белый, чёрный, серый) из набора убираем.
  // Они попадают сюда из `--accent-contrast` (#ffffff у PROFK), но брендовой
  // идентичности не несут и в интерфейсе живут как нейтрали: гейт на
  // `rgba(255,255,255,0.02)` дал бы десятки ложных срабатываний и приучил бы
  // ставить `brand-allow` не думая — то есть обессмыслил бы сам маркер.
  for (const t of [...triples]) {
    const [r, g, b] = t.split(',').map(Number)
    if (r === g && g === b) {
      triples.delete(t)
      hexes.delete(tripleToHex(t))
    }
  }

  if (hexes.size === 0) {
    console.error(
      `✖ brand-hardcode guard: в ${relative(SRC, TOKENS_CSS)} не найдено ни одного ` +
        '`--*accent*`-объявления. Гейт без набора цветов бессмысленен — ' +
        'проверь, не переехали ли токены.',
    )
    process.exit(1)
  }
  return { hexes, triples }
}

const { hexes, triples } = brandColorsFromTokens()

const PATTERNS = [
  // Сырой бренд-hex.
  ...[...hexes].map((h) => new RegExp(h.replace('#', '#'), 'i')),
  // Тот же цвет каналами: rgb()/rgba(), пробелы и дробная альфа допустимы.
  ...[...triples].map((t) => {
    const [r, g, b] = t.split(',')
    return new RegExp(`rgba?\\(\\s*${r}\\s*,\\s*${g}\\s*,\\s*${b}\\s*[,)]`, 'i')
  }),
  // Палитра публичного табло: живёт инлайн в ResidentBoardPage (в SKIP_FILES),
  // в остальных файлах — такой же сырой литерал, как брендовый accent.
  /#1a6b52/i,
  // Имена лого-файлов: путь к ассету обязан идти через brand.logoMark.
  /infrasafe-logo\.svg/i,
  /profk-(?:mark|logo|favicon)\.svg/i,
]

/** @param {string} dir @param {string[]} out */
function walk(dir, out) {
  for (const name of readdirSync(dir)) {
    const full = join(dir, name)
    if (statSync(full).isDirectory()) {
      walk(full, out)
    } else if (/\.(tsx?|css)$/.test(name) && !/\.test\.tsx?$/.test(name)) {
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

console.log(
  `✓ brand-hardcode guard: чисто (${files.length} файлов, ` +
    `${hexes.size} брендовых цветов из токенов).`,
)
