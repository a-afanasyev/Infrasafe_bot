import { useState } from 'react'
import {
  usePendingModeration,
  useApproveModeration,
  useRejectModeration,
} from '../../hooks/useAddresses'
import type { ModerationItem } from '../../types/api'
import EmptyState from '../shared/EmptyState'
import LoadingSpinner from '../shared/LoadingSpinner'

// ── Styles ───────────────────────────────────────────────────────────

const cardStyle: React.CSSProperties = {
  background: 'var(--bg-card)',
  border: '1px solid var(--border)',
  borderRadius: 'var(--radius)',
  padding: '16px 20px',
  display: 'flex',
  flexDirection: 'column',
  gap: 10,
}

const nameStyle: React.CSSProperties = {
  fontFamily: 'var(--font-display)',
  fontWeight: 600,
  fontSize: 15,
  color: 'var(--text-primary)',
}

const detailStyle: React.CSSProperties = {
  fontSize: 13,
  color: 'var(--text-secondary)',
  fontFamily: 'var(--font-display)',
  lineHeight: 1.5,
}

const badgeBase: React.CSSProperties = {
  borderRadius: 12,
  padding: '2px 10px',
  fontSize: 11,
  fontWeight: 600,
  fontFamily: 'var(--font-mono)',
  display: 'inline-block',
}

const ownerBadge: React.CSSProperties = {
  ...badgeBase,
  background: 'rgba(16, 185, 129, 0.13)',
  color: 'var(--emerald, #10b981)',
}

const tenantBadge: React.CSSProperties = {
  ...badgeBase,
  background: 'rgba(59, 130, 246, 0.13)',
  color: 'var(--blue, #3b82f6)',
}

const approveBtnStyle: React.CSSProperties = {
  background: 'var(--accent)',
  border: 'none',
  borderRadius: 8,
  cursor: 'pointer',
  fontSize: 13,
  color: '#fff',
  padding: '7px 14px',
  fontFamily: 'var(--font-display)',
  fontWeight: 600,
}

const rejectBtnStyle: React.CSSProperties = {
  background: 'var(--red, #ef4444)',
  border: 'none',
  borderRadius: 8,
  cursor: 'pointer',
  fontSize: 13,
  color: '#fff',
  padding: '7px 14px',
  fontFamily: 'var(--font-display)',
  fontWeight: 600,
}

const textareaStyle: React.CSSProperties = {
  width: '100%',
  padding: '8px 12px',
  background: 'var(--bg-surface)',
  border: '1px solid var(--border)',
  borderRadius: 'var(--radius-sm)',
  color: 'var(--text-primary)',
  fontSize: 13,
  outline: 'none',
  fontFamily: 'var(--font-display)',
  boxSizing: 'border-box',
  resize: 'vertical',
  minHeight: 60,
}

const cancelLinkStyle: React.CSSProperties = {
  background: 'none',
  border: 'none',
  cursor: 'pointer',
  fontSize: 13,
  color: 'var(--text-muted)',
  fontFamily: 'var(--font-display)',
  textDecoration: 'underline',
  padding: 0,
}

const sendBtnStyle: React.CSSProperties = {
  background: 'var(--red, #ef4444)',
  border: 'none',
  borderRadius: 8,
  cursor: 'pointer',
  fontSize: 13,
  color: '#fff',
  padding: '7px 14px',
  fontFamily: 'var(--font-display)',
  fontWeight: 600,
}

// ── Component ────────────────────────────────────────────────────────

export default function ModerationPanel() {
  const { data: items = [], isLoading } = usePendingModeration()
  const approve = useApproveModeration()
  const reject = useRejectModeration()

  const [rejectingId, setRejectingId] = useState<number | null>(null)
  const [rejectComment, setRejectComment] = useState('')

  if (isLoading) return <LoadingSpinner />

  if (items.length === 0) {
    return (
      <EmptyState
        icon="&#10003;"
        title="Нет заявок на модерацию"
        subtitle="Все заявки рассмотрены"
      />
    )
  }

  const handleApprove = (id: number) => {
    approve.mutate(id)
  }

  const handleStartReject = (id: number) => {
    setRejectingId(id)
    setRejectComment('')
  }

  const handleCancelReject = () => {
    setRejectingId(null)
    setRejectComment('')
  }

  const handleSubmitReject = (id: number) => {
    if (rejectComment.trim().length < 3) return
    reject.mutate(
      { id, comment: rejectComment.trim() },
      { onSuccess: () => handleCancelReject() },
    )
  }

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return null
    return new Date(dateStr).toLocaleDateString('ru-RU')
  }

  const buildAddress = (item: ModerationItem) => {
    const parts: string[] = []
    if (item.yard_name) parts.push(item.yard_name)
    if (item.building_address) parts.push(item.building_address)
    parts.push(`кв. ${item.apartment_number}`)
    return parts.join(' / ')
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {items.map(item => (
        <div key={item.id} style={cardStyle}>
          {/* Top row: name + badge */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
            <span style={nameStyle}>
              {item.user_name || 'Без имени'}
            </span>
            {item.user_phone && (
              <span style={{ fontSize: 13, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                {item.user_phone}
              </span>
            )}
            <span style={item.is_owner ? ownerBadge : tenantBadge}>
              {item.is_owner ? 'Собственник' : 'Жилец'}
            </span>
          </div>

          {/* Address */}
          <div style={detailStyle}>
            {buildAddress(item)}
          </div>

          {/* Date */}
          {item.requested_at && (
            <div style={{ fontSize: 12, color: 'var(--text-muted)', fontFamily: 'var(--font-display)' }}>
              Заявка от {formatDate(item.requested_at)}
            </div>
          )}

          {/* Actions */}
          {rejectingId === item.id ? (
            /* Rejection form */
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <textarea
                value={rejectComment}
                onChange={e => setRejectComment(e.target.value)}
                placeholder="Причина отклонения (мин. 3 символа)"
                style={textareaStyle}
                autoFocus
              />
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <button
                  onClick={() => handleSubmitReject(item.id)}
                  disabled={rejectComment.trim().length < 3 || reject.isPending}
                  style={{
                    ...sendBtnStyle,
                    opacity: rejectComment.trim().length < 3 || reject.isPending ? 0.6 : 1,
                    cursor: rejectComment.trim().length < 3 || reject.isPending ? 'not-allowed' : 'pointer',
                  }}
                >
                  {reject.isPending ? 'Отправка...' : 'Отправить'}
                </button>
                <button onClick={handleCancelReject} style={cancelLinkStyle}>
                  Отмена
                </button>
              </div>
            </div>
          ) : (
            /* Approve / Reject buttons */
            <div style={{ display: 'flex', gap: 8 }}>
              <button
                onClick={() => handleApprove(item.id)}
                disabled={approve.isPending}
                style={{
                  ...approveBtnStyle,
                  opacity: approve.isPending ? 0.6 : 1,
                  cursor: approve.isPending ? 'not-allowed' : 'pointer',
                }}
              >
                Одобрить
              </button>
              <button
                onClick={() => handleStartReject(item.id)}
                style={rejectBtnStyle}
              >
                Отклонить
              </button>
            </div>
          )}
        </div>
      ))}
    </div>
  )
}
