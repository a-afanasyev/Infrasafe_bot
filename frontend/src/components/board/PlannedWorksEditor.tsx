import { useTranslation } from 'react-i18next'
import { Plus, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import type { PlannedWorkCfg } from '../../types/boardConfig'
import { todayInDisplayTz } from '../../utils/timezone'
import LocalizedField from './LocalizedField'

// Потолок списка — как на бэкенде (MAX_PLANNED_WORKS в board_config/schemas.py).
export const MAX_PLANNED_WORKS = 20

interface PlannedWorksEditorProps {
  works: PlannedWorkCfg[]
  onChange: (works: PlannedWorkCfg[]) => void
}

const EMPTY = { ru: '', uz: '' }

// Плановые работы для блока «Ближайшие работы» страницы жителей. Каждая правка
// отдаёт НОВЫЙ список — черновик редактора не мутируется.
export default function PlannedWorksEditor({ works, onChange }: PlannedWorksEditorProps) {
  const { t } = useTranslation()

  const update = (idx: number, patch: Partial<PlannedWorkCfg>) =>
    onChange(works.map((w, i) => (i === idx ? { ...w, ...patch } : w)))

  const add = () =>
    onChange([
      ...works,
      {
        id: `pw-${Date.now()}`,
        date: todayInDisplayTz(),
        time_from: '',
        time_to: '',
        title: EMPTY,
        place: EMPTY,
        text: EMPTY,
      },
    ])

  return (
    <>
      <p className="text-xs text-text-muted">{t('boardEditor.plannedWorksHint')}</p>
      {works.map((w, idx) => (
        <div key={w.id} className="rounded-sm border border-border-default bg-bg-surface p-3" data-testid="planned-work">
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <label className="flex items-center gap-1 text-xs text-text-muted">
              {t('boardEditor.workDate')}
              <Input
                type="date"
                className="w-36"
                value={w.date}
                onChange={(e) => { if (e.target.value) update(idx, { date: e.target.value }) }}
              />
            </label>
            <label className="flex items-center gap-1 text-xs text-text-muted">
              {t('boardEditor.workTimeFrom')}
              <Input type="time" className="w-28" value={w.time_from} onChange={(e) => update(idx, { time_from: e.target.value })} />
            </label>
            <label className="flex items-center gap-1 text-xs text-text-muted">
              {t('boardEditor.workTimeTo')}
              <Input type="time" className="w-28" value={w.time_to} onChange={(e) => update(idx, { time_to: e.target.value })} />
            </label>
            <button
              type="button"
              aria-label="remove"
              className="ml-auto text-text-muted hover:text-red-500"
              onClick={() => onChange(works.filter((_, i) => i !== idx))}
            >
              <Trash2 size={16} />
            </button>
          </div>
          <div className="flex flex-col gap-2">
            <LocalizedField label={t('boardEditor.workTitle')} value={w.title} onChange={(v) => update(idx, { title: v })} />
            <LocalizedField label={t('boardEditor.workPlace')} value={w.place} onChange={(v) => update(idx, { place: v })} />
            <LocalizedField label={t('boardEditor.workText')} value={w.text} textarea onChange={(v) => update(idx, { text: v })} />
          </div>
        </div>
      ))}
      <Button variant="outline" size="sm" onClick={add} disabled={works.length >= MAX_PLANNED_WORKS}>
        <Plus size={14} className="mr-1" />
        {t('boardEditor.addPlannedWork')}
      </Button>
    </>
  )
}
