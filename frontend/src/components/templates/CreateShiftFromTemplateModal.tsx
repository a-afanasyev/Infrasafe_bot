import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useCreateShiftFromTemplate } from '../../hooks/useTemplates'
import { useEmployees } from '../../hooks/useEmployees'
import type { EmployeeBrief } from '../../types/api'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { cn } from '@/lib/utils'

interface Props {
  isOpen: boolean
  onClose: () => void
  templateId: number | null
  templateName?: string
}

function employeeName(e: EmployeeBrief): string {
  const full = [e.first_name, e.last_name].filter(Boolean).join(' ').trim()
  return full || e.phone || `#${e.id}`
}

function today(): string {
  return new Date().toISOString().split('T')[0]
}

export default function CreateShiftFromTemplateModal({ isOpen, onClose, templateId, templateName }: Props) {
  const { t } = useTranslation()
  const createFromTemplate = useCreateShiftFromTemplate()
  const { data: employees = [], isLoading } = useEmployees()

  const [date, setDate] = useState(today)
  const [selected, setSelected] = useState<number[]>([])
  const [error, setError] = useState<string | null>(null)

  // Reset to defaults each time the modal is (re)opened so a previous row's
  // selection never leaks into the next create.
  useEffect(() => {
    if (isOpen) {
      setDate(today())
      setSelected([])
      setError(null)
    }
  }, [isOpen])

  const toggle = (id: number) =>
    setSelected((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]))

  const handleSubmit = () => {
    setError(null)
    if (!date) {
      setError(t('errors.shiftDateRequired'))
      return
    }
    if (selected.length === 0) {
      setError(t('errors.executorsRequired'))
      return
    }
    if (templateId == null) return
    createFromTemplate.mutate(
      { template_id: templateId, date, user_ids: selected },
      { onSuccess: () => onClose() },
    )
  }

  return (
    <Dialog open={isOpen} onOpenChange={(open) => { if (!open) onClose() }}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {t('templates.createShiftTitle')}
            {templateName ? ` — ${templateName}` : ''}
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label>{t('templates.shiftDate')}</Label>
            <Input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
          </div>

          <div className="space-y-1.5">
            <Label>{t('templates.selectExecutors')}</Label>
            {isLoading ? (
              <p className="text-[13px] text-muted-foreground">{t('common.loading')}</p>
            ) : employees.length === 0 ? (
              <p className="text-[13px] text-muted-foreground">{t('templates.noExecutors')}</p>
            ) : (
              <div className="flex flex-wrap gap-2">
                {employees.map((e) => (
                  <button
                    key={e.id}
                    type="button"
                    onClick={() => toggle(e.id)}
                    className={cn(
                      'px-3 py-1.5 rounded-sm border text-[13px] transition-colors',
                      selected.includes(e.id)
                        ? 'bg-primary text-primary-foreground border-primary'
                        : 'bg-transparent border-border-default hover:bg-accent',
                    )}
                  >
                    {employeeName(e)}
                  </button>
                ))}
              </div>
            )}
          </div>

          {error && (
            <div className="text-[13px] text-red bg-red/10 border border-red/30 rounded-sm px-3 py-2.5">
              {error}
            </div>
          )}
        </div>

        <DialogFooter>
          <Button type="button" variant="outline" onClick={onClose}>
            {t('common.cancel')}
          </Button>
          <Button type="button" onClick={handleSubmit} disabled={createFromTemplate.isPending}>
            {createFromTemplate.isPending ? t('common.creating') : t('templates.createShift')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
