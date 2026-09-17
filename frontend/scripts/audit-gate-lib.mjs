// Чистая часть npm-audit гейта (без процесса и exit): валидация формы отчёта и
// применение политики. Раннер — audit-gate.mjs; тесты — audit-gate.test.mjs.

export const BLOCKING = new Set(['high', 'critical'])

const isObject = (v) => typeof v === 'object' && v !== null && !Array.isArray(v)

// AUD7-ENG-01: «проверка не состоялась» ≠ «находок нет». npm при недоступном
// registry печатает синтаксически корректный JSON `{message, error: {…}}`,
// а при чужой схеме — что угодно без `vulnerabilities`. Оба случая раньше
// сводились к пустому списку advisory и exit 0. Возвращает строку-причину или
// null, если отчёт пригоден для оценки.
export function validateReport(report) {
  if (!isObject(report)) return 'report is not a JSON object'
  if ('error' in report) {
    const msg = typeof report.message === 'string' ? report.message : JSON.stringify(report.error)
    return `npm audit reported an error instead of a report: ${msg}`
  }
  if (!isObject(report.vulnerabilities)) return 'report has no `vulnerabilities` object'
  if (!isObject(report.metadata?.vulnerabilities)) return 'report has no `metadata.vulnerabilities` object'
  return null
}

// Плоский список конкретных advisory (via-объекты; via-строки — это транзитивные
// ссылки на другой пакет, собственного advisory не несут).
export function flattenAdvisories(vulns) {
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
  return advisories
}

// Политика: high/critical вне allowlist блокируют; запись allowlist, которая
// больше ничего не матчит, — тоже (не копим мёртвые ignore'ы).
export function evaluateReport(report, allowlist) {
  const advisories = flattenAdvisories(report.vulnerabilities)
  const allowed = new Map(allowlist.map((e) => [e.id, e]))
  const blocking = advisories.filter((a) => BLOCKING.has(a.severity) && !allowed.has(a.ghsa))
  const suppressed = advisories.filter((a) => allowed.has(a.ghsa))
  const stale = allowlist.filter((e) => !advisories.some((a) => a.ghsa === e.id))
  return {
    ok: blocking.length === 0 && stale.length === 0,
    blocking,
    suppressed,
    stale,
    counts: report.metadata.vulnerabilities,
    allowed,
  }
}
