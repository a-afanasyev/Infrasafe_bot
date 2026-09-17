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
//     → тоже exit 1: заставляет удалить запись, а не копить мёртвые ignore'ы;
//   • несостоявшаяся проверка (registry недоступен, невалидный JSON, отчёт
//     без `vulnerabilities`/`metadata`) → exit 2 (AUD7-ENG-01: раньше
//     `{error}` читался как «0 находок» и гейт молча проходил).
//
// Проверяется только prod-дерево (`--omit=dev`) — так по дизайну: runtime
// фронта — статика за nginx (frontend/Dockerfile), dev-инструменты в образ
// не попадают. Их advisory — сопровождение (AUD7-DEP-01), не blocking-гейт.
//
// Чистая логика — audit-gate-lib.mjs (тесты в audit-gate.test.mjs).

import { execFileSync } from 'node:child_process'

import { evaluateReport, validateReport } from './audit-gate-lib.mjs'

// Обоснованные исключения. Каждая запись — конкретный GHSA, НЕ пакет целиком:
//   { id: 'GHSA-xxxx-xxxx-xxxx', package: 'name', added: 'YYYY-MM-DD', reason: '…' }
// Формат reason: почему код-путь недостижим ИЛИ почему патча нет — и что
// снимет запись. Пустой список — нормальное состояние: сначала пытаемся
// закрыть находку бампом, allowlist только когда бампа не существует.
//
// История: GHSA-qwww-vcr4-c8h2 (react-router, RSC-only) добавлялся 2026-07-25 и
// снят в тот же день — апгрейд react-router 7.18.1 → 8.3.0 закрыл его по-настоящему.
const ALLOWLIST = []

const EXIT_FINDINGS = 1
const EXIT_AUDIT_FAILED = 2

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

function fail(reason) {
  console.log(`::error::npm audit did not produce a usable report — ${reason}`)
  process.exit(EXIT_AUDIT_FAILED)
}

let report
try {
  report = JSON.parse(runAudit())
} catch (err) {
  fail(err.message)
}

const invalid = validateReport(report)
if (invalid) fail(invalid)

const { ok, blocking, suppressed, stale, counts, allowed } = evaluateReport(report, ALLOWLIST)

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

console.log(
  `npm audit (prod deps): critical=${counts.critical ?? 0} high=${counts.high ?? 0} ` +
    `moderate=${counts.moderate ?? 0} low=${counts.low ?? 0}; ` +
    `blocking=${blocking.length}, allowlisted=${suppressed.length}, stale-allowlist=${stale.length}`,
)

process.exit(ok ? 0 : EXIT_FINDINGS)
