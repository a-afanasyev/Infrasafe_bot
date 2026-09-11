import type { ReactNode } from 'react'

/**
 * Named section: heading + count badge, hidden entirely when the group is
 * empty (EmployeesPage.tsx pending-block shape). Used once per work-report
 * status group on WorkReportsPage. `actions` — групповые действия справа в
 * шапке (например, «Отклонить всех без медиа» у группы модерации).
 */
export default function GroupSection({
  title,
  count,
  actions,
  children,
}: {
  title: string
  count: number
  actions?: ReactNode
  children: ReactNode
}) {
  if (count === 0) return null
  return (
    <div className="bg-bg-card border border-border-default rounded-default p-5">
      <div className="flex items-center justify-between gap-2 mb-4 flex-wrap">
        <div className="flex items-center gap-2">
          <span className="font-[var(--font-display)] font-semibold text-sm text-text-primary">{title}</span>
          <span className="bg-amber/20 text-amber rounded-full px-2 py-0.5 text-[11px] font-semibold">{count}</span>
        </div>
        {actions}
      </div>
      <div className="flex flex-col gap-2">{children}</div>
    </div>
  )
}
