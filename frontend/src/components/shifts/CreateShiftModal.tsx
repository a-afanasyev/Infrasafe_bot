import { useState, useEffect } from 'react'
import { useCreateShift } from '../../hooks/useShifts'
import { useEmployees } from '../../hooks/useEmployees'
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

export default function CreateShiftModal({ isOpen, onClose }: Props) {
  const createShift = useCreateShift()

  const [executorId, setExecutorId] = useState('')
  const [startTime, setStartTime] = useState('')
  const [endTime, setEndTime] = useState('')
  const [shiftType, setShiftType] = useState('regular')
  const [maxRequests, setMaxRequests] = useState('10')
  const [priority, setPriority] = useState('3')
  const [notes, setNotes] = useState('')
  const [specFocus, setSpecFocus] = useState<string[]>([])
  const [error, setError] = useState<string | null>(null)

  const { data: employees = [] } = useEmployees({}, undefined)

  useEffect(() => {
    if (isOpen) {
      setExecutorId('')
      setStartTime('')
      setEndTime('')
      setShiftType('regular')
      setMaxRequests('10')
      setPriority('3')
      setNotes('')
      setSpecFocus([])
      setError(null)
    }
  }, [isOpen])

  if (!isOpen) return null

  const toggleSpec = (spec: string) => {
    setSpecFocus(prev => prev.includes(spec) ? prev.filter(s => s !== spec) : [...prev, spec])
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    if (!executorId) { setError('Выберите исполнителя'); return }
    if (!startTime) {
      setError('Укажите время начала смены')
      return
    }
    if (!endTime) {
      setError('Укажите время окончания смены')
      return
    }
    if (new Date(endTime) <= new Date(startTime)) {
      setError('Время окончания должно быть позже времени начала')
      return
    }

    try {
      await createShift.mutateAsync({
        user_id: Number(executorId),
        start_time: new Date(startTime).toISOString(),
        end_time: endTime ? new Date(endTime).toISOString() : undefined,
        shift_type: shiftType,
        max_requests: Number(maxRequests),
        priority_level: Number(priority),
        notes: notes || undefined,
        specialization_focus: specFocus,
      })
      onClose()
      // Reset form
      setExecutorId('')
      setStartTime('')
      setEndTime('')
      setShiftType('regular')
      setMaxRequests('10')
      setPriority('3')
      setNotes('')
      setSpecFocus([])
    } catch (err: unknown) {
      const msg =
        err instanceof Error ? err.message : 'Ошибка при создании смены'
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
      onClick={e => { if (e.target === e.currentTarget) onClose() }}
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
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <h2
            style={{
              margin: 0,
              fontFamily: 'var(--font-display)',
              fontSize: '18px',
              fontWeight: 700,
              color: 'var(--text-primary)',
            }}
          >
            Создать смену
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
          {/* Executor */}
          <div>
            <label style={labelStyle}>Исполнитель</label>
            <select
              value={executorId}
              onChange={e => setExecutorId(e.target.value)}
              style={inputStyle}
            >
              <option value="">— Выберите исполнителя —</option>
              {employees.map(emp => (
                <option key={emp.id} value={String(emp.id)}>
                  {[emp.first_name, emp.last_name].filter(Boolean).join(' ') || `ID ${emp.id}`}
                  {emp.phone ? ` · ${emp.phone}` : ''}
                </option>
              ))}
            </select>
          </div>

          {/* Start time */}
          <div>
            <label style={labelStyle}>Начало смены</label>
            <input
              type="datetime-local"
              value={startTime}
              onChange={e => setStartTime(e.target.value)}
              style={inputStyle}
            />
          </div>

          {/* End time */}
          <div>
            <label style={labelStyle}>Конец смены</label>
            <input
              type="datetime-local"
              value={endTime}
              onChange={e => setEndTime(e.target.value)}
              style={inputStyle}
            />
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
                <option key={t.value} value={t.value}>{t.label}</option>
              ))}
            </select>
          </div>

          {/* Specializations */}
          <div style={{ marginBottom: '16px' }}>
            <label style={{ display: 'block', fontSize: '12px', color: 'var(--text-muted)', marginBottom: '6px' }}>
              Специализации
            </label>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
              {Object.entries(SPEC_DISPLAY).map(([key, label]) => (
                <button
                  key={key}
                  type="button"
                  onClick={() => toggleSpec(key)}
                  style={{
                    padding: '4px 10px', borderRadius: 20, fontSize: '12px', cursor: 'pointer',
                    background: specFocus.includes(key) ? 'var(--accent-dim)' : 'var(--bg-surface)',
                    color: specFocus.includes(key) ? 'var(--accent)' : 'var(--text-secondary)',
                    border: `1px solid ${specFocus.includes(key) ? 'var(--border-active)' : 'var(--border)'}`,
                    fontFamily: 'var(--font-body)',
                  }}
                >{label}</button>
              ))}
            </div>
          </div>

          {/* Max requests */}
          <div>
            <label style={labelStyle}>Макс. заявок</label>
            <input
              type="number"
              min={1}
              value={maxRequests}
              onChange={e => setMaxRequests(e.target.value)}
              style={inputStyle}
            />
          </div>

          {/* Priority */}
          <div>
            <label style={labelStyle}>Приоритет</label>
            <select
              value={priority}
              onChange={e => setPriority(e.target.value)}
              style={inputStyle}
            >
              {PRIORITIES.map(p => (
                <option key={p.value} value={p.value}>{p.label}</option>
              ))}
            </select>
          </div>

          {/* Notes */}
          <div>
            <label style={labelStyle}>Заметки</label>
            <textarea
              value={notes}
              onChange={e => setNotes(e.target.value)}
              rows={3}
              placeholder="Дополнительная информация..."
              style={{ ...inputStyle, resize: 'vertical' }}
            />
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
              disabled={createShift.isPending}
              style={{
                padding: '10px 20px',
                borderRadius: 'var(--radius-sm)',
                background: 'var(--accent)',
                border: 'none',
                color: '#000',
                fontSize: '14px',
                fontWeight: 700,
                cursor: createShift.isPending ? 'not-allowed' : 'pointer',
                fontFamily: 'var(--font-body)',
                opacity: createShift.isPending ? 0.7 : 1,
              }}
            >
              {createShift.isPending ? 'Создание...' : 'Создать'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
