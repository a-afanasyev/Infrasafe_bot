import type { ReactNode } from 'react'

/**
 * Named section: heading + count badge, hidden entirely when the group is
 * empty (EmployeesPage.tsx pending-block shape). Used once per work-report
 * status group on WorkReportsPage.
 */
export default function GroupSection({
  title,
  count,
  children,
}: {
  title: string
  count: number
  children: ReactNode
}) {
  if (count === 0) return null
  return (
    <div className="bg-bg-card border border-border-default rounded-default p-5">
      <div className="flex items-center gap-2 mb-4">
        <span className="font-[var(--font-display)] font-semibold text-sm text-text-primary">{title}</span>
        <span className="bg-amber/20 text-amber rounded-full px-2 py-0.5 text-[11px] font-semibold">{count}</span>
      </div>
      <div className="flex flex-col gap-2">{children}</div>
    </div>
  )
}
