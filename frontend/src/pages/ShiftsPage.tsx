import { useState, useEffect } from 'react'
import { useTopbar } from '../contexts/TopbarContext'
import {
  useShiftSchedule,
  useShiftStats,
  useShiftTransfers,
  useShiftTemplates,
} from '../hooks/useShifts'
import ShiftTimeline from '../components/shifts/ShiftTimeline'
import ShiftCoverageHeatmap from '../components/shifts/ShiftCoverageHeatmap'
import CreateShiftModal from '../components/shifts/CreateShiftModal'
import ShiftDetailModal from '../components/shifts/ShiftDetailModal'
import LoadingSpinner from '../components/shared/LoadingSpinner'
import { ChevronLeft, ChevronRight } from 'lucide-react'

export default function ShiftsPage() {
  const { setActions, clearActions } = useTopbar()
  const [selectedDate, setSelectedDate] = useState(new Date())
  const [createModalOpen, setCreateModalOpen] = useState(false)
  const [selectedShiftId, setSelectedShiftId] = useState<number | null>(null)

  const dateStr = selectedDate.toISOString().split('T')[0]
  const nextDay = new Date(selectedDate)
  nextDay.setDate(nextDay.getDate() + 1)
  const nextDayStr = nextDay.toISOString().split('T')[0]

  const { data: shifts = [], isLoading: shiftsLoading } = useShiftSchedule(
    dateStr + 'T00:00:00Z',
    nextDayStr + 'T00:00:00Z',
  )
  const { data: stats } = useShiftStats()
  const { data: transfers = [] } = useShiftTransfers()
  const { data: templates = [] } = useShiftTemplates()

  const goToday = () => setSelectedDate(new Date())
  const goPrev = () =>
    setSelectedDate(d => {
      const n = new Date(d)
      n.setDate(n.getDate() - 1)
      return n
    })
  const goNext = () =>
    setSelectedDate(d => {
      const n = new Date(d)
      n.setDate(n.getDate() + 1)
      return n
    })

  // Topbar actions
  useEffect(() => {
    setActions(
      <div style={{ display: 'flex', gap: '8px' }}>
        <button
          onClick={() => {}}
          style={{
            padding: '8px 14px',
            borderRadius: 'var(--radius-sm)',
            fontSize: '13px',
            fontWeight: 600,
            cursor: 'pointer',
            fontFamily: 'var(--font-body)',
            background: 'var(--bg-surface)',
            border: '1px solid var(--border)',
            color: 'var(--text-secondary)',
          }}
        >
          Шаблоны
        </button>
        <button
          onClick={() => setCreateModalOpen(true)}
          style={{
            padding: '8px 14px',
            borderRadius: 'var(--radius-sm)',
            fontSize: '13px',
            fontWeight: 600,
            cursor: 'pointer',
            fontFamily: 'var(--font-body)',
            background: 'var(--accent)',
            color: '#000',
            border: 'none',
          }}
        >
          + Создать смену
        </button>
      </div>,
    )
    return clearActions
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  if (shiftsLoading) return <LoadingSpinner />

  // Date label in Russian
  const dayNames = [
    'Воскресенье',
    'Понедельник',
    'Вторник',
    'Среда',
    'Четверг',
    'Пятница',
    'Суббота',
  ]
  const monthNames = [
    'января',
    'февраля',
    'марта',
    'апреля',
    'мая',
    'июня',
    'июля',
    'августа',
    'сентября',
    'октября',
    'ноября',
    'декабря',
  ]
  const dateLabelStr = `${dayNames[selectedDate.getDay()]}, ${selectedDate.getDate()} ${monthNames[selectedDate.getMonth()]} ${selectedDate.getFullYear()}`

  const avgLoad =
    shifts.length > 0
      ? Math.round(
          shifts.reduce((s, sh) => s + sh.load_percentage, 0) / shifts.length,
        )
      : 0

  const STATS_CARDS = [
    {
      label: 'Исполнителей на смене',
      value: `${stats?.active_executors ?? 0}`,
      color: 'var(--accent)',
    },
    {
      label: 'Покрытие %',
      value: `${stats?.coverage_pct ?? 0}%`,
      color: 'var(--blue)',
    },
    {
      label: 'Ср. нагрузка',
      value: `${avgLoad}%`,
      color: 'var(--emerald)',
    },
    {
      label: 'Передачи',
      value: `${stats?.pending_transfers ?? 0}`,
      color: 'var(--amber)',
    },
    {
      label: 'Смен сегодня',
      value: `${stats?.shifts_today ?? 0}`,
      color: 'var(--violet)',
    },
  ]

  const navBtnStyle: React.CSSProperties = {
    width: 36,
    height: 36,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    background: 'var(--bg-surface)',
    border: '1px solid var(--border)',
    borderRadius: 'var(--radius-sm)',
    cursor: 'pointer',
    color: 'var(--text-secondary)',
  }

  return (
    <div
      style={{
        padding: '20px 24px',
        display: 'flex',
        flexDirection: 'column',
        gap: '20px',
      }}
    >
      {/* Date navigation */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
        <button onClick={goPrev} style={navBtnStyle}>
          <ChevronLeft size={16} />
        </button>
        <button onClick={goNext} style={navBtnStyle}>
          <ChevronRight size={16} />
        </button>
        <span
          style={{
            fontFamily: 'var(--font-display)',
            fontWeight: 600,
            fontSize: '16px',
            color: 'var(--text-primary)',
          }}
        >
          {dateLabelStr}
        </span>
        <button
          onClick={goToday}
          style={{
            padding: '4px 12px',
            borderRadius: 20,
            background: 'var(--accent-dim)',
            color: 'var(--accent)',
            border: '1px solid var(--border-active)',
            fontSize: '12px',
            fontWeight: 600,
            cursor: 'pointer',
          }}
        >
          Сегодня
        </button>
      </div>

      {/* Stats cards */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(5, 1fr)',
          gap: '12px',
        }}
      >
        {STATS_CARDS.map(card => (
          <div
            key={card.label}
            style={{
              background: 'var(--bg-card)',
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius)',
              padding: '16px',
              position: 'relative',
              overflow: 'hidden',
            }}
          >
            <div
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: '24px',
                fontWeight: 600,
                color: card.color,
                marginBottom: '4px',
              }}
            >
              {card.value}
            </div>
            <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
              {card.label}
            </div>
            <div
              style={{
                position: 'absolute',
                bottom: 0,
                left: 0,
                right: 0,
                height: '3px',
                background: card.color,
                opacity: 0.4,
              }}
            />
          </div>
        ))}
      </div>

      {/* Timeline */}
      <div
        style={{
          background: 'var(--bg-card)',
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius)',
          overflow: 'hidden',
        }}
      >
        <div
          style={{
            padding: '16px 20px 12px',
            borderBottom: '1px solid var(--border)',
            fontFamily: 'var(--font-display)',
            fontWeight: 600,
            fontSize: '14px',
            color: 'var(--text-primary)',
          }}
        >
          Расписание смен
        </div>
        <ShiftTimeline
          shifts={shifts}
          date={selectedDate}
          onShiftClick={s => setSelectedShiftId(s.id)}
        />
      </div>

      {/* Bottom panels */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: '1fr 380px',
          gap: '20px',
        }}
      >
        {/* Heatmap */}
        <div
          style={{
            background: 'var(--bg-card)',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius)',
            padding: '20px',
          }}
        >
          <div
            style={{
              fontFamily: 'var(--font-display)',
              fontWeight: 600,
              fontSize: '14px',
              color: 'var(--text-primary)',
              marginBottom: '16px',
            }}
          >
            Тепловая карта покрытия
          </div>
          <ShiftCoverageHeatmap shifts={shifts} date={selectedDate} />
        </div>

        {/* Transfers + Templates */}
        <div
          style={{
            background: 'var(--bg-card)',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius)',
            padding: '20px',
            display: 'flex',
            flexDirection: 'column',
            gap: '16px',
          }}
        >
          {/* Transfers */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span
              style={{
                fontFamily: 'var(--font-display)',
                fontWeight: 600,
                fontSize: '14px',
                color: 'var(--text-primary)',
              }}
            >
              Запросы на передачу
            </span>
            {transfers.length > 0 && (
              <span
                style={{
                  background: 'rgba(245,158,11,0.2)',
                  color: 'var(--amber)',
                  borderRadius: 20,
                  padding: '2px 8px',
                  fontSize: '11px',
                  fontWeight: 600,
                }}
              >
                {transfers.length}
              </span>
            )}
          </div>

          {transfers.length === 0 ? (
            <div
              style={{
                fontSize: '13px',
                color: 'var(--text-muted)',
                textAlign: 'center',
                padding: '12px 0',
              }}
            >
              Нет запросов на передачу
            </div>
          ) : (
            transfers.slice(0, 3).map(t => (
              <div
                key={t.id}
                style={{
                  display: 'flex',
                  alignItems: 'flex-start',
                  gap: '8px',
                  padding: '10px',
                  background: 'var(--bg-surface)',
                  borderRadius: 'var(--radius-sm)',
                }}
              >
                <div
                  style={{
                    width: 8,
                    height: 8,
                    borderRadius: '50%',
                    background:
                      t.urgency_level === 'critical'
                        ? 'var(--red)'
                        : t.urgency_level === 'high'
                          ? 'var(--amber)'
                          : 'var(--blue)',
                    marginTop: 4,
                    flexShrink: 0,
                  }}
                />
                <div style={{ flex: 1, overflow: 'hidden' }}>
                  <div
                    style={{
                      fontSize: '12px',
                      color: 'var(--text-primary)',
                      fontWeight: 600,
                      whiteSpace: 'nowrap',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                    }}
                  >
                    {t.from_executor_name} → {t.to_executor_name ?? '?'}
                  </div>
                  <div
                    style={{
                      fontSize: '11px',
                      color: 'var(--text-muted)',
                      marginTop: 2,
                    }}
                  >
                    {t.reason}
                  </div>
                </div>
              </div>
            ))
          )}

          {/* Templates */}
          <div style={{ borderTop: '1px solid var(--border)', paddingTop: '12px' }}>
            <div
              style={{
                fontFamily: 'var(--font-display)',
                fontWeight: 600,
                fontSize: '13px',
                color: 'var(--text-primary)',
                marginBottom: '10px',
              }}
            >
              Шаблоны смен
            </div>
            {templates.slice(0, 3).map(tmpl => (
              <div
                key={tmpl.id}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '10px',
                  padding: '8px 0',
                  borderBottom: '1px solid var(--border)',
                }}
              >
                <div
                  style={{
                    width: 32,
                    height: 32,
                    borderRadius: 8,
                    background: 'var(--accent-dim)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontSize: '16px',
                    flexShrink: 0,
                  }}
                >
                  📋
                </div>
                <div style={{ flex: 1, overflow: 'hidden' }}>
                  <div
                    style={{
                      fontSize: '12px',
                      fontWeight: 600,
                      color: 'var(--text-primary)',
                      whiteSpace: 'nowrap',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                    }}
                  >
                    {tmpl.name}
                  </div>
                  <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                    {`${tmpl.start_hour}:${String(tmpl.start_minute).padStart(2, '0')} · ${tmpl.duration_hours}ч`}
                  </div>
                </div>
              </div>
            ))}
            {templates.length === 0 && (
              <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                Нет шаблонов
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Modals */}
      <CreateShiftModal
        isOpen={createModalOpen}
        onClose={() => setCreateModalOpen(false)}
      />
      <ShiftDetailModal
        shiftId={selectedShiftId}
        onClose={() => setSelectedShiftId(null)}
      />
    </div>
  )
}
