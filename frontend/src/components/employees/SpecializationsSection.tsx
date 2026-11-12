import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import { SPECIALIZATIONS } from '@/constants/specializations'
import { cn } from '@/lib/utils'
import { getSpecDisplay } from '@/utils/employeeUtils'
import { useSetSpecializations } from '../../hooks/useEmployees'

interface Props {
  employeeId: number
  /** Сохранённые специализации исполнителя. */
  current: string[]
}

/**
 * Специализации исполнителя в карточке сотрудника. Раньше задавались только
 * в инвайте и в боте: исполнитель, получивший роль галочкой в «Ролях»,
 * оставался без специализации и не попадал в подбор по заявкам.
 */
export default function SpecializationsSection({ employeeId, current }: Props) {
  const { t } = useTranslation()
  const save = useSetSpecializations(employeeId)
  // Черновик привязан к сохранённому набору: пришли новые данные — черновик устарел.
  const base = [...current].sort().join(',')
  const [stored, setStored] = useState<{ base: string; specs: string[] } | null>(null)
  const chosen = stored?.base === base ? stored.specs : current
  const dirty = [...chosen].sort().join(',') !== base

  const toggle = (key: string) =>
    setStored({ base, specs: chosen.includes(key) ? chosen.filter((s) => s !== key) : [...chosen, key] })

  return (
    <section
      aria-labelledby="employee-specs-title"
      className="bg-bg-card border border-border-default rounded-default p-5 flex flex-col gap-3"
    >
      <div>
        <div id="employee-specs-title" className="text-[13px] font-semibold text-text-primary">
          {t('employeeDetail.specializations.title')}
        </div>
        <div className={cn('text-[11px] mt-0.5', chosen.length === 0 ? 'text-amber' : 'text-text-muted')}>
          {t(chosen.length === 0 ? 'employeeDetail.specializations.empty' : 'employeeDetail.specializations.hint')}
        </div>
      </div>
      <div className="flex flex-wrap gap-1.5">
        {SPECIALIZATIONS.map((key) => {
          const on = chosen.includes(key)
          return (
            <button
              key={key}
              type="button"
              aria-pressed={on}
              onClick={() => toggle(key)}
              className={cn(
                'px-3 py-1.5 rounded-full text-xs border cursor-pointer transition-all',
                on ? 'bg-accent border-accent text-white font-semibold' : 'bg-bg-card border-border-default text-text-secondary',
              )}
            >
              {getSpecDisplay(key, t)}
            </button>
          )
        })}
      </div>
      {dirty && (
        <div className="flex gap-2">
          <Button
            size="sm"
            disabled={save.isPending}
            onClick={() => save.mutate(chosen, { onSuccess: () => setStored(null) })}
          >
            {t('rbac.save')}
          </Button>
          <Button size="sm" variant="outline" onClick={() => setStored(null)}>
            {t('common.cancel')}
          </Button>
        </div>
      )}
    </section>
  )
}
