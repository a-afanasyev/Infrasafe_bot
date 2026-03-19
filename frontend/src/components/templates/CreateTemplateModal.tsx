import { useState } from 'react'
import { useCreateTemplate } from '../../hooks/useTemplates'
import type { CreateTemplatePayload } from '../../types/api'
import { SPEC_DISPLAY } from '../../utils/employeeUtils'
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
import { Select } from '@/components/ui/select'
import { cn } from '@/lib/utils'

interface Props {
  isOpen: boolean
  onClose: () => void
}

const SHIFT_TYPES = [
  { value: 'regular', label: 'Обычная' },
  { value: 'emergency', label: 'Экстренная' },
  { value: 'overtime', label: 'Сверхурочная' },
  { value: 'maintenance', label: 'Техническое обслуживание' },
]

const PRIORITIES = [
  { value: '1', label: '1 — Низкий' },
  { value: '2', label: '2' },
  { value: '3', label: '3 — Средний' },
  { value: '4', label: '4' },
  { value: '5', label: '5 — Высокий' },
]

const DAY_LABELS = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']

const START_MINUTES = [0, 15, 30, 45]

export default function CreateTemplateModal({ isOpen, onClose }: Props) {
  const createTemplate = useCreateTemplate()

  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [startHour, setStartHour] = useState('9')
  const [startMinute, setStartMinute] = useState('0')
  const [durationHours, setDurationHours] = useState('8')
  const [shiftType, setShiftType] = useState('regular')
  const [daysOfWeek, setDaysOfWeek] = useState<number[]>([0, 1, 2, 3, 4])
  const [selectedSpecs, setSelectedSpecs] = useState<string[]>([])
  const [minExecutors, setMinExecutors] = useState('1')
  const [maxExecutors, setMaxExecutors] = useState('5')
  const [defaultMaxRequests, setDefaultMaxRequests] = useState('10')
  const [priority, setPriority] = useState('3')
  const [autoCreate, setAutoCreate] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (!isOpen) return null

  const toggleDay = (day: number) => {
    setDaysOfWeek(prev =>
      prev.includes(day) ? prev.filter(d => d !== day) : [...prev, day],
    )
  }

  const toggleSpec = (spec: string) => {
    setSelectedSpecs(prev =>
      prev.includes(spec) ? prev.filter(s => s !== spec) : [...prev, spec],
    )
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    if (!name.trim()) {
      setError('Введите название шаблона')
      return
    }
    if (Number(minExecutors) > Number(maxExecutors)) {
      setError('Минимум исполнителей не может превышать максимум')
      return
    }
    try {
      const payload: CreateTemplatePayload = {
        name: name.trim(),
        description: description.trim() || null,
        start_hour: Number(startHour),
        start_minute: Number(startMinute),
        duration_hours: Number(durationHours),
        default_shift_type: shiftType,
        days_of_week: daysOfWeek.length > 0 ? daysOfWeek : undefined,
        min_executors: Number(minExecutors),
        max_executors: Number(maxExecutors),
        auto_create: autoCreate,
        required_specializations: selectedSpecs.length > 0 ? selectedSpecs : undefined,
        default_max_requests: Number(defaultMaxRequests),
        priority_level: Number(priority),
      }
      await createTemplate.mutateAsync(payload)
      onClose()
      // Reset form
      setName('')
      setDescription('')
      setStartHour('9')
      setStartMinute('0')
      setDurationHours('8')
      setShiftType('regular')
      setDaysOfWeek([0, 1, 2, 3, 4])
      setSelectedSpecs([])
      setMinExecutors('1')
      setMaxExecutors('5')
      setDefaultMaxRequests('10')
      setPriority('3')
      setAutoCreate(false)
    } catch (err: unknown) {
      const msg =
        err instanceof Error ? err.message : 'Ошибка при создании шаблона'
      setError(msg)
    }
  }

  return (
    <Dialog open={isOpen} onOpenChange={(open) => { if (!open) onClose() }}>
      <DialogContent className="max-w-[520px] max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Создать шаблон смены</DialogTitle>
        </DialogHeader>

        <form
          onSubmit={handleSubmit}
          className="flex flex-col gap-4"
        >
          {/* Name */}
          <div className="space-y-1.5">
            <Label className="text-xs uppercase tracking-wider text-text-secondary">Название *</Label>
            <Input
              type="text"
              value={name}
              onChange={e => setName(e.target.value)}
              placeholder="Например: Дневная смена"
            />
          </div>

          {/* Description */}
          <div className="space-y-1.5">
            <Label className="text-xs uppercase tracking-wider text-text-secondary">Описание</Label>
            <Input
              type="text"
              value={description}
              onChange={e => setDescription(e.target.value)}
              placeholder="Краткое описание (необязательно)"
            />
          </div>

          {/* Time + Duration */}
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label className="text-xs uppercase tracking-wider text-text-secondary">Начало смены</Label>
              <div className="grid grid-cols-2 gap-2">
                <Input
                  type="number"
                  min={0}
                  max={23}
                  value={startHour}
                  onChange={e => setStartHour(e.target.value)}
                  placeholder="Часы (0-23)"
                />
                <Select
                  value={startMinute}
                  onChange={e => setStartMinute(e.target.value)}
                >
                  {START_MINUTES.map(m => (
                    <option key={m} value={String(m)}>
                      :{String(m).padStart(2, '0')}
                    </option>
                  ))}
                </Select>
              </div>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs uppercase tracking-wider text-text-secondary">Длительность (часов)</Label>
              <Input
                type="number"
                min={1}
                max={24}
                value={durationHours}
                onChange={e => setDurationHours(e.target.value)}
              />
            </div>
          </div>

          {/* Shift type */}
          <div className="space-y-1.5">
            <Label className="text-xs uppercase tracking-wider text-text-secondary">Тип смены</Label>
            <Select
              value={shiftType}
              onChange={e => setShiftType(e.target.value)}
            >
              {SHIFT_TYPES.map(t => (
                <option key={t.value} value={t.value}>
                  {t.label}
                </option>
              ))}
            </Select>
          </div>

          {/* Days of week */}
          <div className="space-y-1.5">
            <Label className="text-xs uppercase tracking-wider text-text-secondary">Дни недели</Label>
            <div className="flex gap-1.5">
              {DAY_LABELS.map((label, idx) => {
                const active = daysOfWeek.includes(idx)
                return (
                  <button
                    key={idx}
                    type="button"
                    onClick={() => toggleDay(idx)}
                    className={cn(
                      'w-9 h-9 rounded-sm text-xs font-semibold cursor-pointer border',
                      active
                        ? 'bg-accent-dim text-accent border-border-active'
                        : 'bg-bg-surface text-text-muted border-border-default'
                    )}
                  >
                    {label}
                  </button>
                )
              })}
            </div>
          </div>

          {/* Required specializations */}
          <div className="space-y-1.5">
            <Label className="text-xs uppercase tracking-wider text-text-secondary">Требуемые специализации</Label>
            <div className="flex flex-wrap gap-1.5">
              {Object.entries(SPEC_DISPLAY).map(([key, label]) => {
                const active = selectedSpecs.includes(key)
                return (
                  <button
                    key={key}
                    type="button"
                    onClick={() => toggleSpec(key)}
                    className={cn(
                      'px-2.5 py-1 rounded-full text-xs cursor-pointer border',
                      active
                        ? 'bg-accent-dim text-accent border-border-active'
                        : 'bg-bg-surface text-text-secondary border-border-default'
                    )}
                  >
                    {label}
                  </button>
                )
              })}
            </div>
          </div>

          {/* Executors + max requests */}
          <div className="grid grid-cols-3 gap-3">
            <div className="space-y-1.5">
              <Label className="text-xs uppercase tracking-wider text-text-secondary">Мин. исполнителей</Label>
              <Input
                type="number"
                min={1}
                value={minExecutors}
                onChange={e => setMinExecutors(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs uppercase tracking-wider text-text-secondary">Макс. исполнителей</Label>
              <Input
                type="number"
                min={1}
                value={maxExecutors}
                onChange={e => setMaxExecutors(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs uppercase tracking-wider text-text-secondary">Макс. заявок</Label>
              <Input
                type="number"
                min={1}
                value={defaultMaxRequests}
                onChange={e => setDefaultMaxRequests(e.target.value)}
              />
            </div>
          </div>

          {/* Priority + auto create */}
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label className="text-xs uppercase tracking-wider text-text-secondary">Приоритет</Label>
              <Select
                value={priority}
                onChange={e => setPriority(e.target.value)}
              >
                {PRIORITIES.map(p => (
                  <option key={p.value} value={p.value}>
                    {p.label}
                  </option>
                ))}
              </Select>
            </div>
            <div className="flex flex-col justify-end space-y-1.5">
              <Label className="text-xs uppercase tracking-wider text-text-secondary">Авто-создание</Label>
              <label className="flex items-center gap-2.5 cursor-pointer h-9">
                {/* Toggle switch */}
                <div
                  onClick={() => setAutoCreate(v => !v)}
                  className={cn(
                    'w-10 h-[22px] rounded-full border border-border-default relative cursor-pointer transition-colors duration-200 shrink-0',
                    autoCreate ? 'bg-accent' : 'bg-bg-surface'
                  )}
                >
                  <div
                    className="absolute top-0.5 w-4 h-4 rounded-full bg-white shadow-[0_1px_3px_rgba(0,0,0,0.3)] transition-[left] duration-200"
                    style={{ left: autoCreate ? 20 : 2 }}
                  />
                </div>
                <span className="text-[13px] text-text-secondary">
                  {autoCreate ? 'Включено' : 'Выключено'}
                </span>
              </label>
            </div>
          </div>

          {/* Error */}
          {error && (
            <div className="text-[13px] text-red bg-red/10 border border-red/30 rounded-sm px-3 py-2.5">
              {error}
            </div>
          )}

          {/* Actions */}
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={onClose}
            >
              Отмена
            </Button>
            <Button
              type="submit"
              disabled={createTemplate.isPending}
            >
              {createTemplate.isPending ? 'Создание...' : 'Создать шаблон'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
