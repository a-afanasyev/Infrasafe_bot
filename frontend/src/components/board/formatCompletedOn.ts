// Shared with pages/WorkReportsArchivePage.tsx — extracted per T12 code
// review (was duplicated verbatim in both files). Split into its own file
// (rather than living alongside WorkReportPhoto.tsx) so that file can stay
// component-only for react-refresh/only-export-components.

// "YYYY-MM-DD" (date-only, per PublicWorkReport.completed_on) → "DD.MM.YYYY".
// Deliberately NOT reusing ResidentBoardPage's formatPublished — that one
// expects a full datetime ISO string with a time component.
// Regex, not new Date(dateOnly) — Date parses "YYYY-MM-DD" as UTC midnight,
// which renders as the previous day in timezones behind UTC.
export function formatCompletedOn(dateOnly: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(dateOnly)
  if (!m) return dateOnly
  const [, y, mo, d] = m
  return `${d}.${mo}.${y}`
}
