import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiClient } from '../../api/client'

const URGENCY: Record<string, { bg: string; color: string }> = {
  'Обычная':    { bg: 'rgba(16,185,129,0.12)',  color: '#10b981' },
  'Средняя':    { bg: 'rgba(245,158,11,0.12)',  color: '#d97706' },
  'Срочная':    { bg: 'rgba(249,115,22,0.12)',  color: '#ea580c' },
  'Критическая':{ bg: 'rgba(239,68,68,0.12)',   color: '#dc2626' },
}

const STATUS: Record<string, { bg: string; color: string }> = {
  'Новая':     { bg: 'rgba(59,130,246,0.12)',  color: '#3b82f6'  },
  'В работе':  { bg: 'rgba(245,158,11,0.12)',  color: '#d97706'  },
  'Закуп':     { bg: 'rgba(139,92,246,0.12)',  color: '#7c3aed'  },
  'Уточнение': { bg: 'rgba(6,182,212,0.12)',   color: '#0891b2'  },
  'Выполнена': { bg: 'rgba(16,185,129,0.12)',  color: '#059669'  },
  'Исполнено': { bg: 'rgba(0,212,170,0.12)',   color: '#00a884'  },
  'Принято':   { bg: 'rgba(34,197,94,0.12)',   color: '#16a34a'  },
  'Отменена':  { bg: 'rgba(239,68,68,0.12)',   color: '#dc2626'  },
}

const SOURCE_ICON: Record<string, string> = {
  bot: '🤖', twa: '📱', web: '🌐', call_center: '📞',
}

interface Props {
  requestNumber: string | null
  onClose: () => void
}

export default function RequestDetailModal({ requestNumber, onClose }: Props) {
  const queryClient = useQueryClient()
  const [comment, setComment] = useState('')
  const [confirmNote, setConfirmNote] = useState('')
  const [showConfirmSection, setShowConfirmSection] = useState(false)
  const [showReturnSection, setShowReturnSection] = useState(false)
  const [returnReason, setReturnReason] = useState('')

  useEffect(() => {
    setComment('')
    setConfirmNote('')
    setShowConfirmSection(false)
    setShowReturnSection(false)
    setReturnReason('')
  }, [requestNumber])

  const { data: request } = useQuery({
    queryKey: ['request', requestNumber],
    queryFn: () => apiClient.get(`/api/v2/requests/${requestNumber}`).then(r => r.data),
    enabled: !!requestNumber,
  })

  const { data: comments } = useQuery({
    queryKey: ['comments', requestNumber],
    queryFn: () => apiClient.get(`/api/v2/requests/${requestNumber}/comments`).then(r => r.data),
    enabled: !!requestNumber,
  })

  const updateRequest = useMutation({
    mutationFn: (data: Record<string, unknown>) =>
      apiClient.patch(`/api/v2/requests/${requestNumber}`, data).then(r => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['request', requestNumber] })
      queryClient.invalidateQueries({ queryKey: ['kanban'] })
      setShowConfirmSection(false)
      setConfirmNote('')
    },
  })

  const postComment = useMutation({
    mutationFn: (text: string) =>
      apiClient.post(`/api/v2/requests/${requestNumber}/comments`, { text, is_internal: true }).then(r => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['comments', requestNumber] })
      setComment('')
    },
  })

  if (!requestNumber) return null

  const statusStyle = STATUS[request?.status ?? ''] ?? { bg: 'rgba(100,116,139,0.12)', color: '#64748b' }
  const urgencyStyle = request?.urgency ? URGENCY[request.urgency] : null

  const inputStyle: React.CSSProperties = {
    background: 'var(--bg-surface)',
    border: '1px solid var(--border)',
    borderRadius: 10,
    padding: '8px 12px',
    fontSize: 13,
    color: 'var(--text-primary)',
    fontFamily: 'var(--font-body)',
    outline: 'none',
    width: '100%',
    boxSizing: 'border-box',
  }

  return (
    <div
      style={{
        position: 'fixed', inset: 0,
        background: 'rgba(0,0,0,0.5)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        zIndex: 50,
        backdropFilter: 'blur(4px)',
      }}
      onClick={onClose}
    >
      <div
        style={{
          background: 'var(--bg-card)',
          border: '1px solid var(--border)',
          borderRadius: 16,
          width: '100%',
          maxWidth: 520,
          maxHeight: '88vh',
          boxShadow: '0 24px 64px rgba(0,0,0,0.4)',
          display: 'flex',
          flexDirection: 'column',
        }}
        onClick={e => e.stopPropagation()}
      >
        {!request ? (
          <div style={{ padding: 24, textAlign: 'center', color: 'var(--text-muted)', fontFamily: 'var(--font-body)' }}>
            Загрузка...
          </div>
        ) : (
          <>
            {/* Header */}
            <div style={{
              padding: '16px 18px 14px',
              borderBottom: '1px solid var(--border)',
              flexShrink: 0,
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'flex-start',
            }}>
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)' }}>
                    {request.request_number}
                  </span>
                  <span style={{ fontSize: 13 }}>{SOURCE_ICON[request.source ?? ''] ?? ''}</span>
                </div>
                <div style={{
                  fontFamily: 'var(--font-display)',
                  fontWeight: 700,
                  fontSize: 18,
                  color: 'var(--text-primary)',
                  lineHeight: 1.2,
                }}>
                  {request.category}
                </div>
              </div>
              <button
                onClick={onClose}
                style={{
                  background: 'none', border: 'none', cursor: 'pointer',
                  color: 'var(--text-muted)', fontSize: 18, lineHeight: 1,
                  padding: '2px 4px', borderRadius: 4,
                }}
              >×</button>
            </div>

            {/* Body */}
            <div style={{ padding: '16px 18px', overflowY: 'auto', flex: 1, display: 'flex', flexDirection: 'column', gap: 14 }}>

              {/* Badges */}
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                <span style={{
                  fontSize: 12, fontWeight: 600, padding: '4px 10px', borderRadius: 20,
                  background: statusStyle.bg, color: statusStyle.color,
                  fontFamily: 'var(--font-display)',
                }}>{request.status}</span>
                {urgencyStyle && (
                  <span style={{
                    fontSize: 12, fontWeight: 600, padding: '4px 10px', borderRadius: 20,
                    background: urgencyStyle.bg, color: urgencyStyle.color,
                    fontFamily: 'var(--font-display)',
                  }}>{request.urgency}</span>
                )}
                {request.manager_confirmed && (
                  <span style={{
                    fontSize: 12, fontWeight: 600, padding: '4px 10px', borderRadius: 20,
                    background: 'rgba(16,185,129,0.12)', color: '#059669',
                    fontFamily: 'var(--font-display)',
                  }}>✓ Подтверждено</span>
                )}
              </div>

              {/* Description */}
              {request.description && (
                <p style={{ fontSize: 14, color: 'var(--text-primary)', lineHeight: 1.55, margin: 0 }}>
                  {request.description}
                </p>
              )}

              {/* Meta */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                  Создана: {new Date(request.created_at).toLocaleString('ru')}
                </div>
                {request.executor_name && (
                  <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                    Исполнитель: <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{request.executor_name}</span>
                  </div>
                )}
                {request.address && (
                  <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                    Адрес: {request.address}
                  </div>
                )}
              </div>

              {/* Contextual blocks */}
              {request.requested_materials && (
                <div style={{ background: 'rgba(245,158,11,0.08)', border: '1px solid rgba(245,158,11,0.2)', borderRadius: 10, padding: '10px 12px', fontSize: 13 }}>
                  <span style={{ fontWeight: 600, color: '#d97706' }}>Закуп: </span>
                  <span style={{ color: 'var(--text-primary)' }}>{request.requested_materials}</span>
                </div>
              )}
              {request.notes && (
                <div style={{ background: 'rgba(59,130,246,0.08)', border: '1px solid rgba(59,130,246,0.2)', borderRadius: 10, padding: '10px 12px', fontSize: 13 }}>
                  <span style={{ fontWeight: 600, color: '#3b82f6' }}>Уточнение: </span>
                  <span style={{ color: 'var(--text-primary)' }}>{request.notes}</span>
                </div>
              )}
              {request.completion_report && (
                <div style={{ background: 'rgba(16,185,129,0.08)', border: '1px solid rgba(16,185,129,0.2)', borderRadius: 10, padding: '10px 12px', fontSize: 13 }}>
                  <span style={{ fontWeight: 600, color: '#059669' }}>Отчёт: </span>
                  <span style={{ color: 'var(--text-primary)' }}>{request.completion_report}</span>
                </div>
              )}
              {request.return_reason && (
                <div style={{ background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.2)', borderRadius: 10, padding: '10px 12px', fontSize: 13 }}>
                  <span style={{ fontWeight: 600, color: '#dc2626' }}>Возврат: </span>
                  <span style={{ color: 'var(--text-primary)' }}>{request.return_reason}</span>
                </div>
              )}

              {/* Manager actions */}
              {request.status === 'Выполнена' && (
                <div style={{ border: '1px solid var(--border)', borderRadius: 12, padding: 12, background: 'var(--bg-surface)', display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {!showConfirmSection && !showReturnSection && (
                    <div style={{ display: 'flex', gap: 8 }}>
                      <button
                        onClick={() => setShowConfirmSection(true)}
                        style={{ flex: 1, background: '#059669', color: '#fff', border: 'none', borderRadius: 8, padding: '8px 0', fontSize: 13, fontWeight: 600, cursor: 'pointer', fontFamily: 'var(--font-display)' }}
                      >✓ Подтвердить</button>
                      <button
                        onClick={() => setShowReturnSection(true)}
                        style={{ flex: 1, background: 'none', border: '1px solid #ea580c', color: '#ea580c', borderRadius: 8, padding: '8px 0', fontSize: 13, fontWeight: 600, cursor: 'pointer', fontFamily: 'var(--font-display)' }}
                      >↩ Вернуть в работу</button>
                    </div>
                  )}
                  {showConfirmSection && (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                      <p style={{ fontSize: 12, color: 'var(--text-secondary)', margin: 0 }}>Комментарий (необязательно):</p>
                      <textarea style={{ ...inputStyle, minHeight: 60, resize: 'vertical' }} placeholder="Всё выполнено качественно" value={confirmNote} onChange={e => setConfirmNote(e.target.value)} />
                      <div style={{ display: 'flex', gap: 8 }}>
                        <button onClick={() => setShowConfirmSection(false)} style={{ flex: 1, background: 'none', border: '1px solid var(--border)', borderRadius: 8, padding: '6px 0', fontSize: 13, color: 'var(--text-secondary)', cursor: 'pointer' }}>Отмена</button>
                        <button onClick={() => updateRequest.mutate({ status: 'Исполнено', manager_confirmed: true, ...(confirmNote ? { manager_confirmation_notes: confirmNote } : {}) })} disabled={updateRequest.isPending} style={{ flex: 1, background: '#059669', color: '#fff', border: 'none', borderRadius: 8, padding: '6px 0', fontSize: 13, fontWeight: 600, cursor: 'pointer', opacity: updateRequest.isPending ? 0.5 : 1 }}>
                          {updateRequest.isPending ? 'Сохраняю...' : 'Подтвердить'}
                        </button>
                      </div>
                    </div>
                  )}
                  {showReturnSection && (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                      <p style={{ fontSize: 12, color: 'var(--text-secondary)', margin: 0 }}>Причина возврата:</p>
                      <textarea style={{ ...inputStyle, minHeight: 60, resize: 'vertical' }} placeholder="Опишите что нужно доделать" value={returnReason} onChange={e => setReturnReason(e.target.value)} autoFocus />
                      <div style={{ display: 'flex', gap: 8 }}>
                        <button onClick={() => setShowReturnSection(false)} style={{ flex: 1, background: 'none', border: '1px solid var(--border)', borderRadius: 8, padding: '6px 0', fontSize: 13, color: 'var(--text-secondary)', cursor: 'pointer' }}>Отмена</button>
                        <button onClick={() => updateRequest.mutate({ status: 'В работе', return_reason: returnReason.trim() })} disabled={updateRequest.isPending || !returnReason.trim()} style={{ flex: 1, background: '#ea580c', color: '#fff', border: 'none', borderRadius: 8, padding: '6px 0', fontSize: 13, fontWeight: 600, cursor: 'pointer', opacity: (updateRequest.isPending || !returnReason.trim()) ? 0.5 : 1 }}>
                          {updateRequest.isPending ? 'Сохраняю...' : 'Вернуть'}
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* Comments history */}
              {comments && comments.length > 0 && (
                <div>
                  <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.5px', fontFamily: 'var(--font-display)', marginBottom: 8 }}>История</div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                    {comments.map((c: { id: number; comment_text: string; is_internal: boolean; created_at: string }) => (
                      <div key={c.id} style={{
                        borderRadius: 10, padding: '10px 12px', fontSize: 13,
                        background: c.is_internal ? 'rgba(245,158,11,0.07)' : 'var(--bg-surface)',
                        border: `1px solid ${c.is_internal ? 'rgba(245,158,11,0.15)' : 'var(--border)'}`,
                      }}>
                        <p style={{ margin: '0 0 4px', color: 'var(--text-primary)' }}>{c.comment_text}</p>
                        <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>{new Date(c.created_at).toLocaleString('ru')}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Add comment */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.5px', fontFamily: 'var(--font-display)' }}>Заметка менеджера</div>
                <div style={{ display: 'flex', gap: 8 }}>
                  <input
                    style={{ ...inputStyle, flex: 1 }}
                    placeholder="Добавить заметку..."
                    value={comment}
                    onChange={e => setComment(e.target.value)}
                    onKeyDown={e => e.key === 'Enter' && comment.trim() && postComment.mutate(comment)}
                  />
                  <button
                    onClick={() => postComment.mutate(comment)}
                    disabled={!comment.trim() || postComment.isPending}
                    style={{
                      background: 'var(--accent)', color: '#001a14',
                      border: 'none', borderRadius: 10,
                      padding: '0 14px', fontSize: 16, cursor: 'pointer',
                      opacity: (!comment.trim() || postComment.isPending) ? 0.4 : 1,
                      flexShrink: 0,
                    }}
                  >↑</button>
                </div>
              </div>

            </div>
          </>
        )}
      </div>
    </div>
  )
}
