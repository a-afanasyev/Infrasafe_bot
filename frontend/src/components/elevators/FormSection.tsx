import { cn } from '@/lib/utils'

/**
 * Карточка-секция модуля «Лифты» (паспорт, форма, конфиг): заголовок +
 * содержимое; `grid` — раскладка полей в 1/2/3 колонки, иначе колонка.
 */
export default function FormSection({
  title,
  grid = true,
  children,
}: {
  title: string
  grid?: boolean
  children: React.ReactNode
}) {
  return (
    <div className="bg-bg-card border border-border-default rounded-default p-4 flex flex-col gap-3">
      <h3 className="text-[13px] font-semibold text-text-primary">{title}</h3>
      <div className={cn(grid ? 'grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3' : 'flex flex-col gap-3')}>
        {children}
      </div>
    </div>
  )
}
