import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient } from '../../api/client'
import { useTWAAuth } from '../../hooks/useTWAAuth'

const STATUS_ORDER = ['Новая', 'В работе', 'Закуп', 'Уточнение', 'Выполнена', 'Исполнено', 'Принято']

export default function TWARequestDetailPage() {
  const { isAuthenticated } = useTWAAuth()
  const { number } = useParams<{ number: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [message, setMessage] = useState('')
  const [rating, setRating] = useState(0)
  const [returnReason, setReturnReason] = useState('')
  const [showReturnForm, setShowReturnForm] = useState(false)
  const [sending, setSending] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState('')

  const { data: request } = useQuery({
    queryKey: ['request', number],
    queryFn: () => apiClient.get(`/api/v2/requests/${number}`).then(r => r.data),
    enabled: isAuthenticated && !!number,
  })

  const { data: comments } = useQuery({
    queryKey: ['comments', number],
    queryFn: () => apiClient.get(`/api/v2/requests/${number}/comments`).then(r => r.data),
    enabled: isAuthenticated && !!number,
  })

  if (!number) return <div className="p-4 text-red-500">Заявка не найдена</div>

  const sendMessage = async () => {
    if (!message.trim()) return
    setSending(true)
    try {
      await apiClient.post(`/api/v2/requests/${number}/comments`, { text: message })
      setMessage('')
      queryClient.invalidateQueries({ queryKey: ['comments', number] })
    } finally {
      setSending(false)
    }
  }

  const handleAccept = async () => {
    if (isSubmitting) return
    setSubmitError('')
    setIsSubmitting(true)
    try {
      const payload: Record<string, unknown> = { status: 'Принято' }
      if (rating > 0) payload.rating = rating
      await apiClient.patch(`/api/v2/requests/${number}`, payload)
      queryClient.invalidateQueries({ queryKey: ['request', number] })
      navigate('/twa')
    } catch {
      setSubmitError('Не удалось сохранить. Попробуйте снова.')
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleReturn = async () => {
    if (isSubmitting) return
    if (!returnReason.trim()) return
    setSubmitError('')
    setIsSubmitting(true)
    try {
      await apiClient.patch(`/api/v2/requests/${number}`, {
        status: 'В работе',
        return_reason: returnReason.trim(),
      })
      queryClient.invalidateQueries({ queryKey: ['request', number] })
      navigate('/twa')
    } catch {
      setSubmitError('Не удалось сохранить. Попробуйте снова.')
    } finally {
      setIsSubmitting(false)
    }
  }

  if (!request) return <div className="p-4 text-gray-400">Загрузка...</div>

  const showAcceptance = request.status === 'Исполнено' || (request.status === 'Выполнена' && request.manager_confirmed)
  const currentIdx = STATUS_ORDER.indexOf(request.status)

  return (
    <div className="flex flex-col min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white border-b p-4">
        <button onClick={() => navigate('/twa')} className="text-blue-600 text-sm mb-2">&larr; Назад</button>
        <div className="flex justify-between items-start">
          <div>
            <span className="font-mono text-xs text-gray-500">{request.request_number}</span>
            <h2 className="font-bold">{request.category}</h2>
          </div>
          <span className="text-xs px-2 py-1 rounded-full bg-blue-100 text-blue-700">{request.status}</span>
        </div>
        <p className="text-sm text-gray-600 mt-2">{request.description}</p>
      </div>

      {/* Status timeline */}
      <div className="bg-white border-b p-4 overflow-x-auto">
        {request.status === 'Отменена' ? (
          <div className="flex gap-2 items-center text-sm text-red-500">
            <span>🚫</span><span>Заявка отменена</span>
          </div>
        ) : (
          <div className="flex gap-1 min-w-max">
            {STATUS_ORDER.map((s, i) => (
              <div key={s} className={`text-xs px-2 py-1 rounded ${i <= currentIdx ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-400'}`}>
                {s}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Comments */}
      <div className="flex-1 overflow-y-auto p-4 space-y-2">
        {(comments ?? []).map((c: { id: number; comment_text: string; comment_type: string; created_at: string }) => (
          <div key={c.id} className="bg-white rounded-xl p-3 border">
            <p className="text-sm">{c.comment_text}</p>
            <span className="text-xs text-gray-400">{new Date(c.created_at).toLocaleString('ru')}</span>
          </div>
        ))}
      </div>

      {/* Message input */}
      {!showAcceptance && (
        <div className="bg-white border-t p-3 flex gap-2">
          <input
            className="flex-1 border rounded-xl px-3 py-2 text-sm"
            placeholder="Написать сообщение..."
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && sendMessage()}
          />
          <button onClick={sendMessage} disabled={sending || !message.trim()}
            className="bg-blue-600 text-white px-4 py-2 rounded-xl text-sm disabled:opacity-50">
            &uarr;
          </button>
        </div>
      )}

      {/* Acceptance block */}
      {showAcceptance && (
        <div className="bg-white border-t p-4">
          {!showReturnForm ? (
            <>
              <p className="font-medium mb-2">Оцените работу (необязательно)</p>
              <div className="flex gap-2 mb-3">
                {[1, 2, 3, 4, 5].map(n => (
                  <button
                    key={n}
                    onClick={() => setRating(prev => prev === n ? 0 : n)}
                    className={`text-2xl ${n <= rating ? 'text-yellow-400' : 'text-gray-300'}`}
                  >
                    &#9733;
                  </button>
                ))}
              </div>
              {submitError && <div className="text-red-500 text-sm mb-2">{submitError}</div>}
              <div className="flex gap-2">
                <button
                  onClick={() => {
                    setSubmitError('')
                    setShowReturnForm(true)
                  }}
                  disabled={isSubmitting}
                  className="flex-1 border py-2 rounded-xl text-sm disabled:opacity-50"
                >
                  &#8617; Вернуть
                </button>
                <button
                  onClick={handleAccept}
                  disabled={isSubmitting}
                  className="flex-1 bg-blue-600 text-white py-2 rounded-xl text-sm disabled:opacity-50"
                >
                  &#10003; Принять
                </button>
              </div>
            </>
          ) : (
            <>
              <p className="font-medium mb-2">Почему возвращаете?</p>
              <textarea
                className="w-full border rounded-xl p-3 text-sm min-h-[80px] mb-3 focus:outline-none focus:border-blue-500"
                placeholder="Опишите что не так..."
                value={returnReason}
                onChange={e => setReturnReason(e.target.value)}
                autoFocus
              />
              {submitError && <div className="text-red-500 text-sm mb-2">{submitError}</div>}
              <div className="flex gap-2">
                <button
                  onClick={() => {
                    setSubmitError('')
                    setShowReturnForm(false)
                  }}
                  className="flex-1 border py-2 rounded-xl text-sm"
                >
                  Назад
                </button>
                <button
                  onClick={handleReturn}
                  disabled={!returnReason.trim() || isSubmitting}
                  className="flex-1 bg-red-500 text-white py-2 rounded-xl text-sm disabled:opacity-40"
                >
                  Отправить
                </button>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  )
}
