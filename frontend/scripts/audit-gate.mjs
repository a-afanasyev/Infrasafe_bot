#!/usr/bin/env node
// npm-audit гейт с allowlist'ом. Замена голому `npm audit --audit-level=high`:
// тот падает на ЛЮБОЙ high/critical, даже если уязвимый код-путь у нас
// физически недостижим и патча в пределах semver-диапазона не существует —
// т.е. чинится только мажорным апгрейдом. У `npm audit` своего --ignore нет
// (в отличие от `pip-audit --ignore-vuln`, см. .github/workflows/ci.yml), так
// что фильтрацию делаем здесь — по ЯВНОМУ списку GHSA с обоснованием.
//
// Семантика:
//   • любая high/critical находка ВНЕ allowlist → exit 1 (гейт блокирующий);
//   • moderate/low — информативно, не блокируют (как и было с --audit-level=high);
//   • протухший allowlist (запись больше ничего не матчит — уязвимость ушла)
//     → тоже exit 1: заставляет удалить запись, а не копить мёртвые ignore'ы.

import { execFileSync } from 'node:child_process'

// Обоснованные исключения. Каждая запись — конкретный GHSA, НЕ пакет целиком.
const ALLOWLIST = [
  {
    id: 'GHSA-qwww-vcr4-c8h2',
    package: 'react-router',
    added: '2026-07-25',
    // «RSC Mode CSRF Bypass Allows Action Execution Before 400 Response».
    // Затрагивает ТОЛЬКО React Server Components-режим react-router (RSC
    // server actions). Наш фронт — SPA на Vite: никакого SSR/RSC, роутер
    // используется в declarative/data-режиме (createBrowserRouter/<Routes>),
    // серверных actions нет вовсе → уязвимый путь недостижим. Патч только в
    // react-router 8.3.0 (мажор, миграция v7→v8); внутри ^7 закрыто всё
    // остальное бампом до 7.18.1. Снять при апгрейде на v8.
    reason: 'RSC-only path; SPA build has no SSR/RSC or server actions. Fixed only in v8 (major).',
  },
]

const BLOCKING = new Set(['high', 'critical'])

function runAudit() {
  try {
    // npm audit выходит с кодом 1, когда находки есть, — stdout при этом валиден.
    return execFileSync('npm', ['audit', '--omit=dev', '--json'], {
      encoding: 'utf8',
      maxBuffer: 32 * 1024 * 1024,
    })
  } catch (err) {
    if (typeof err.stdout === 'string' && err.stdout.trim()) return err.stdout
    throw err
  }
}

const report = JSON.parse(runAudit())
const vulns = report.vulnerabilities ?? {}

// Плоский список конкретных advisory (via-объекты; via-строки — это транзитивные
// ссылки на другой пакет, собственного advisory не несут).
const advisories = []
for (const entry of Object.values(vulns)) {
  for (const via of entry.via ?? []) {
    if (typeof via === 'string') continue
    const ghsa = /GHSA-[0-9a-z-]+/i.exec(via.url ?? '')?.[0] ?? `source:${via.source}`
    advisories.push({
      ghsa,
      package: via.name ?? entry.name,
      severity: (via.severity ?? entry.severity ?? 'unknown').toLowerCase(),
      title: via.title ?? '(no title)',
      url: via.url ?? '',
    })
  }
}

const allowed = new Map(ALLOWLIST.map((e) => [e.id, e]))
const blocking = advisories.filter((a) => BLOCKING.has(a.severity) && !allowed.has(a.ghsa))
const suppressed = advisories.filter((a) => allowed.has(a.ghsa))
const stale = ALLOWLIST.filter((e) => !advisories.some((a) => a.ghsa === e.id))

for (const a of suppressed) {
  console.log(`allowlisted: ${a.ghsa} (${a.severity}, ${a.package}) — ${allowed.get(a.ghsa).reason}`)
}

for (const e of stale) {
  console.log(
    `::error::allowlist entry ${e.id} (${e.package}) no longer matches any advisory — remove it from frontend/scripts/audit-gate.mjs`,
  )
}

for (const a of blocking) {
  console.log(`::error::${a.severity} ${a.ghsa} in ${a.package}: ${a.title} ${a.url}`)
}

const counts = report.metadata?.vulnerabilities ?? {}
console.log(
  `npm audit (prod deps): critical=${counts.critical ?? 0} high=${counts.high ?? 0} ` +
    `moderate=${counts.moderate ?? 0} low=${counts.low ?? 0}; ` +
    `blocking=${blocking.length}, allowlisted=${suppressed.length}, stale-allowlist=${stale.length}`,
)

process.exit(blocking.length > 0 || stale.length > 0 ? 1 : 0)
