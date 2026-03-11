import { useState } from 'react'
import { useCreateTemplate, CreateTemplatePayload } from '../../hooks/useTemplates'
import { SPEC_DISPLAY } from '../../utils/employeeUtils'

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
        days_of_week: daysOfWeek.length > 0 ? daysOfWeek : null,
        is_active: true,
        min_executors: Number(minExecutors),
        max_executors: Number(maxExecutors),
        auto_create: autoCreate,
        required_specializations: selectedSpecs.length > 0 ? selectedSpecs : null,
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

  const inputStyle: React.CSSProperties = {
    width: '100%',
    padding: '10px 12px',
    background: 'var(--bg-surface)',
    border: '1px solid var(--border)',
    borderRadius: 'var(--radius-sm)',
    color: 'var(--text-primary)',
    fontSize: '14px',
    fontFamily: 'var(--font-body)',
    outline: 'none',
    boxSizing: 'border-box',
  }

  const labelStyle: React.CSSProperties = {
    display: 'block',
    fontSize: '12px',
    fontWeight: 600,
    color: 'var(--text-secondary)',
    marginBottom: '6px',
    textTransform: 'uppercase',
    letterSpacing: '0.04em',
  }

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(0,0,0,0.6)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 1000,
      }}
      onClick={e => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div
        style={{
          width: '520px',
          maxWidth: '100vw',
          background: 'var(--bg-card)',
          border: '1px solid var(--border)',
          borderRadius: '16px',
          padding: '28px',
          display: 'flex',
          flexDirection: 'column',
          gap: '20px',
          maxHeight: '90vh',
          overflowY: 'auto',
        }}
      >
        {/* Header */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <h2
            style={{
              margin: 0,
              fontFamily: 'var(--font-display)',
              fontSize: '18px',
              fontWeight: 700,
              color: 'var(--text-primary)',
            }}
          >
            Создать шаблон смены
          </h2>
          <button
            onClick={onClose}
            style={{
              background: 'none',
              border: 'none',
              color: 'var(--text-muted)',
              cursor: 'pointer',
              fontSize: '20px',
              lineHeight: 1,
              padding: '4px',
            }}
          >
            ×
          </button>
        </div>

        {/* Form */}
        <form
          onSubmit={handleSubmit}
          style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}
        >
          {/* Name */}
          <div>
            <label style={labelStyle}>Название *</label>
            <input
              type="text"
              value={name}
              onChange={e => setName(e.target.value)}
              placeholder="Например: Дневная смена"
              style={inputStyle}
            />
          </div>

          {/* Description */}
          <div>
            <label style={labelStyle}>Описание</label>
            <input
              type="text"
              value={description}
              onChange={e => setDescription(e.target.value)}
              placeholder="Краткое описание (необязательно)"
              style={inputStyle}
            />
          </div>

          {/* Time + Duration */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
            <div>
              <label style={labelStyle}>Начало смены</label>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px' }}>
                <input
                  type="number"
                  min={0}
                  max={23}
                  value={startHour}
                  onChange={e => setStartHour(e.target.value)}
                  placeholder="Часы (0-23)"
                  style={inputStyle}
                />
                <select
                  value={startMinute}
                  onChange={e => setStartMinute(e.target.value)}
                  style={inputStyle}
                >
                  {START_MINUTES.map(m => (
                    <option key={m} value={String(m)}>
                      :{String(m).padStart(2, '0')}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            <div>
              <label style={labelStyle}>Длительность (часов)</label>
              <input
                type="number"
                min={1}
                max={24}
                value={durationHours}
                onChange={e => setDurationHours(e.target.value)}
                style={inputStyle}
              />
            </div>
          </div>

          {/* Shift type */}
          <div>
            <label style={labelStyle}>Тип смены</label>
            <select
              value={shiftType}
              onChange={e => setShiftType(e.target.value)}
              style={inputStyle}
            >
              {SHIFT_TYPES.map(t => (
                <option key={t.value} value={t.value}>
                  {t.label}
                </option>
              ))}
            </select>
          </div>

          {/* Days of week */}
          <div>
            <label style={labelStyle}>Дни недели</label>
            <div style={{ display: 'flex', gap: '6px' }}>
              {DAY_LABELS.map((label, idx) => {
                const active = daysOfWeek.includes(idx)
                return (
                  <button
                    key={idx}
                    type="button"
                    onClick={() => toggleDay(idx)}
                    style={{
                      width: 36,
                      height: 36,
                      borderRadius: 8,
                      fontSize: '12px',
                      fontWeight: 600,
                      cursor: 'pointer',
                      fontFamily: 'var(--font-body)',
                      background: active ? 'var(--accent-dim)' : 'var(--bg-surface)',
                      color: active ? 'var(--accent)' : 'var(--text-muted)',
                      border: `1px solid ${active ? 'var(--border-active)' : 'var(--border)'}`,
                    }}
                  >
                    {label}
                  </button>
                )
              })}
            </div>
          </div>

          {/* Required specializations */}
          <div>
            <label style={labelStyle}>Требуемые специализации</label>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
              {Object.entries(SPEC_DISPLAY).map(([key, label]) => {
                const active = selectedSpecs.includes(key)
                return (
                  <button
                    key={key}
                    type="button"
                    onClick={() => toggleSpec(key)}
                    style={{
                      padding: '4px 10px',
                      borderRadius: 20,
                      fontSize: '12px',
                      cursor: 'pointer',
                      fontFamily: 'var(--font-body)',
                      background: active ? 'var(--accent-dim)' : 'var(--bg-surface)',
                      color: active ? 'var(--accent)' : 'var(--text-secondary)',
                      border: `1px solid ${active ? 'var(--border-active)' : 'var(--border)'}`,
                    }}
                  >
                    {label}
                  </button>
                )
              })}
            </div>
          </div>

          {/* Executors + max requests */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '12px' }}>
            <div>
              <label style={labelStyle}>Мин. исполнителей</label>
              <input
                type="number"
                min={1}
                value={minExecutors}
                onChange={e => setMinExecutors(e.target.value)}
                style={inputStyle}
              />
            </div>
            <div>
              <label style={labelStyle}>Макс. исполнителей</label>
              <input
                type="number"
                min={1}
                value={maxExecutors}
                onChange={e => setMaxExecutors(e.target.value)}
                style={inputStyle}
              />
            </div>
            <div>
              <label style={labelStyle}>Макс. заявок</label>
              <input
                type="number"
                min={1}
                value={defaultMaxRequests}
                onChange={e => setDefaultMaxRequests(e.target.value)}
                style={inputStyle}
              />
            </div>
          </div>

          {/* Priority + auto create */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
            <div>
              <label style={labelStyle}>Приоритет</label>
              <select
                value={priority}
                onChange={e => setPriority(e.target.value)}
                style={inputStyle}
              >
                {PRIORITIES.map(p => (
                  <option key={p.value} value={p.value}>
                    {p.label}
                  </option>
                ))}
              </select>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', justifyContent: 'flex-end' }}>
              <label style={labelStyle}>Авто-создание</label>
              <label
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '10px',
                  cursor: 'pointer',
                  height: '42px',
                }}
              >
                {/* Toggle switch */}
                <div
                  onClick={() => setAutoCreate(v => !v)}
                  style={{
                    width: 40,
                    height: 22,
                    borderRadius: 11,
                    background: autoCreate ? 'var(--accent)' : 'var(--bg-surface)',
                    border: '1px solid var(--border)',
                    position: 'relative',
                    cursor: 'pointer',
                    transition: 'background 0.2s',
                    flexShrink: 0,
                  }}
                >
                  <div
                    style={{
                      position: 'absolute',
                      top: 2,
                      left: autoCreate ? 20 : 2,
                      width: 16,
                      height: 16,
                      borderRadius: '50%',
                      background: '#fff',
                      transition: 'left 0.2s',
                      boxShadow: '0 1px 3px rgba(0,0,0,0.3)',
                    }}
                  />
                </div>
                <span style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
                  {autoCreate ? 'Включено' : 'Выключено'}
                </span>
              </label>
            </div>
          </div>

          {/* Error */}
          {error && (
            <div
              style={{
                fontSize: '13px',
                color: 'var(--red, #ef4444)',
                background: 'rgba(239,68,68,0.1)',
                border: '1px solid rgba(239,68,68,0.3)',
                borderRadius: 'var(--radius-sm)',
                padding: '10px 12px',
              }}
            >
              {error}
            </div>
          )}

          {/* Actions */}
          <div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end' }}>
            <button
              type="button"
              onClick={onClose}
              style={{
                padding: '10px 20px',
                borderRadius: 'var(--radius-sm)',
                background: 'var(--bg-surface)',
                border: '1px solid var(--border)',
                color: 'var(--text-secondary)',
                fontSize: '14px',
                fontWeight: 600,
                cursor: 'pointer',
                fontFamily: 'var(--font-body)',
              }}
            >
              Отмена
            </button>
            <button
              type="submit"
              disabled={createTemplate.isPending}
              style={{
                padding: '10px 20px',
                borderRadius: 'var(--radius-sm)',
                background: 'var(--accent)',
                border: 'none',
                color: '#000',
                fontSize: '14px',
                fontWeight: 700,
                cursor: createTemplate.isPending ? 'not-allowed' : 'pointer',
                fontFamily: 'var(--font-body)',
                opacity: createTemplate.isPending ? 0.7 : 1,
              }}
            >
              {createTemplate.isPending ? 'Создание...' : 'Создать шаблон'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
