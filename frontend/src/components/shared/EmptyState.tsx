interface EmptyStateProps {
  icon: string
  title: string
  subtitle?: string
  /** Необязательное действие под текстом — когда пустота исправима
   *  (например, страница уехала за конец списка и надо вернуться в начало). */
  action?: React.ReactNode
}

export default function EmptyState({ icon, title, subtitle, action }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-12 px-6 text-text-secondary text-center">
      <span className="text-5xl leading-none">{icon}</span>
      <p className="m-0 font-[family-name:var(--font-display)] text-base font-semibold text-text-primary">{title}</p>
      {subtitle && <p className="m-0 text-sm text-text-muted">{subtitle}</p>}
      {action}
    </div>
  )
}
