// AUD7-ENG-01: гейт npm audit обязан отличать «проверка не состоялась»
// (транспортная ошибка, чужая схема) от «проверка прошла, находок нет».
import { execFileSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import path from 'node:path'
import { describe, expect, it } from 'vitest'

import { evaluateReport, validateReport } from './audit-gate-lib.mjs'

const here = path.dirname(fileURLToPath(import.meta.url))

// Ровно то, что печатает `npm audit --json` при ECONNREFUSED (npm 11, снято 2026-09-17).
const ECONNREFUSED_REPORT = {
  message:
    'request to http://127.0.0.1:9/-/npm/v1/security/advisories/bulk failed, reason: connect ECONNREFUSED 127.0.0.1:9',
  error: { summary: '', detail: '' },
}

const EMPTY_VALID_REPORT = {
  auditReportVersion: 2,
  vulnerabilities: {},
  metadata: {
    vulnerabilities: { info: 0, low: 0, moderate: 0, high: 0, critical: 0, total: 0 },
    dependencies: { prod: 1, dev: 0, optional: 0, peer: 0, peerOptional: 0, total: 1 },
  },
}

function withAdvisory(severity, ghsa = 'GHSA-aaaa-bbbb-cccc') {
  return {
    ...EMPTY_VALID_REPORT,
    vulnerabilities: {
      leftpad: {
        name: 'leftpad',
        severity,
        via: [{ source: 1, name: 'leftpad', severity, title: 'bad', url: `https://github.com/advisories/${ghsa}` }],
      },
    },
    metadata: {
      ...EMPTY_VALID_REPORT.metadata,
      vulnerabilities: { ...EMPTY_VALID_REPORT.metadata.vulnerabilities, [severity]: 1, total: 1 },
    },
  }
}

describe('validateReport', () => {
  it('отклоняет отчёт об ошибке транспорта (ECONNREFUSED)', () => {
    expect(validateReport(ECONNREFUSED_REPORT)).toMatch(/error/i)
  })

  it('отклоняет пустой объект — нет vulnerabilities и metadata', () => {
    expect(validateReport({})).toMatch(/vulnerabilities/)
  })

  it('отклоняет отчёт без metadata.vulnerabilities', () => {
    expect(validateReport({ vulnerabilities: {} })).toMatch(/metadata/)
  })

  it('отклоняет не-объект', () => {
    expect(validateReport(null)).toBeTruthy()
    expect(validateReport('[]')).toBeTruthy()
  })

  it('принимает валидный отчёт без находок', () => {
    expect(validateReport(EMPTY_VALID_REPORT)).toBeNull()
  })
})

describe('evaluateReport', () => {
  it('валидный отчёт без advisory проходит', () => {
    const r = evaluateReport(EMPTY_VALID_REPORT, [])
    expect(r.ok).toBe(true)
    expect(r.blocking).toEqual([])
    expect(r.stale).toEqual([])
  })

  it('high вне allowlist блокирует', () => {
    const r = evaluateReport(withAdvisory('high'), [])
    expect(r.ok).toBe(false)
    expect(r.blocking.map((a) => a.ghsa)).toEqual(['GHSA-aaaa-bbbb-cccc'])
  })

  it('moderate не блокирует', () => {
    expect(evaluateReport(withAdvisory('moderate'), []).ok).toBe(true)
  })

  it('high из allowlist подавляется, запись не протухшая', () => {
    const allow = [{ id: 'GHSA-aaaa-bbbb-cccc', package: 'leftpad', added: '2026-09-17', reason: 'x' }]
    const r = evaluateReport(withAdvisory('high'), allow)
    expect(r.ok).toBe(true)
    expect(r.suppressed.map((a) => a.ghsa)).toEqual(['GHSA-aaaa-bbbb-cccc'])
  })

  it('протухшая запись allowlist валит гейт', () => {
    const allow = [{ id: 'GHSA-dead-dead-dead', package: 'gone', added: '2026-01-01', reason: 'x' }]
    const r = evaluateReport(EMPTY_VALID_REPORT, allow)
    expect(r.ok).toBe(false)
    expect(r.stale.map((e) => e.id)).toEqual(['GHSA-dead-dead-dead'])
  })
})

describe('audit-gate.mjs (интеграция, настоящий npm)', () => {
  it('недоступный registry → ненулевой exit, а не «0 находок»', () => {
    let status = 0
    let output = ''
    try {
      output = execFileSync('node', [path.join(here, 'audit-gate.mjs')], {
        cwd: path.join(here, '..'),
        encoding: 'utf8',
        env: { ...process.env, npm_config_registry: 'http://127.0.0.1:9' },
        stdio: ['ignore', 'pipe', 'pipe'],
      })
    } catch (err) {
      status = err.status
      output = `${err.stdout ?? ''}${err.stderr ?? ''}`
    }
    expect(status).not.toBe(0)
    expect(output).toMatch(/::error::/)
    expect(output).not.toMatch(/blocking=0/)
  }, 60_000)
})
