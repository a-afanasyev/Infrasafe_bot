import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { apiClient } from '../../api/client'
import { useTWAAuth } from '../../hooks/useTWAAuth'
import { tStatus, tCategory } from '../../i18n/apiMaps'
import { formatDate } from '../../i18n/formatters'

const STATUS_ORDER = [
  '\u041D\u043E\u0432\u0430\u044F',
  '\u0412 \u0440\u0430\u0431\u043E\u0442\u0435',
  '\u0417\u0430\u043A\u0443\u043F',
  '\u0423\u0442\u043E\u0447\u043D\u0435\u043D\u0438\u0435',
  '\u0412\u044B\u043F\u043E\u043B\u043D\u0435\u043D\u0430',
  '\u0418\u0441\u043F\u043E\u043B\u043D\u0435\u043D\u043E',
  '\u041F\u0440\u0438\u043D\u044F\u0442\u043E',
]

export default function TWARequestDetailPage() {
  const { t } = useTranslation()
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

  if (!number) return <div className="p-4 text-red-500">{t('errors.requestNotFound')}</div>

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
      const payload: Record<string, unknown> = { status: '\u041F\u0440\u0438\u043D\u044F\u0442\u043E' }
      if (rating > 0) payload.rating = rating
      await apiClient.patch(`/api/v2/requests/${number}`, payload)
      queryClient.invalidateQueries({ queryKey: ['request', number] })
      navigate('/twa')
    } catch {
      setSubmitError(t('errors.saveFailed'))
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
        status: '\u0412 \u0440\u0430\u0431\u043E\u0442\u0435',
        return_reason: returnReason.trim(),
      })
      queryClient.invalidateQueries({ queryKey: ['request', number] })
      navigate('/twa')
    } catch {
      setSubmitError(t('errors.saveFailed'))
    } finally {
      setIsSubmitting(false)
    }
  }

  if (!request) return <div className="p-4 text-gray-400">{t('common.loading')}</div>

  const showAcceptance = request.status === '\u0418\u0441\u043F\u043E\u043B\u043D\u0435\u043D\u043E'
  const currentIdx = STATUS_ORDER.indexOf(request.status)

  return (
    <div className="flex flex-col min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white border-b p-4">
        <button onClick={() => navigate('/twa')} className="text-blue-600 text-sm mb-2">&larr; {t('common.back')}</button>
        <div className="flex justify-between items-start">
          <div>
            <span className="font-mono text-xs text-gray-500">{request.request_number}</span>
            <h2 className="font-bold">{tCategory(request.category, t)}</h2>
          </div>
          <span className="text-xs px-2 py-1 rounded-full bg-blue-100 text-blue-700">{tStatus(request.status, t)}</span>
        </div>
        <p className="text-sm text-gray-600 mt-2">{request.description}</p>
      </div>

      {/* Status timeline */}
      <div className="bg-white border-b p-4 overflow-x-auto">
        {request.status === '\u041E\u0442\u043C\u0435\u043D\u0435\u043D\u0430' ? (
          <div className="flex gap-2 items-center text-sm text-red-500">
            <span>{'\u{1F6AB}'}</span><span>{t('twa.requestCancelled')}</span>
          </div>
        ) : (
          <div className="flex gap-1 min-w-max">
            {STATUS_ORDER.map((s, i) => (
              <div key={s} className={`text-xs px-2 py-1 rounded ${i <= currentIdx ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-400'}`}>
                {tStatus(s, t)}
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
            <span className="text-xs text-gray-400">{formatDate(c.created_at)}</span>
          </div>
        ))}
      </div>

      {/* Message input */}
      {!showAcceptance && (
        <div className="bg-white border-t p-3 flex gap-2">
          <input
            className="flex-1 border rounded-xl px-3 py-2 text-sm"
            placeholder={t('twa.messagePlaceholder')}
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
              <p className="font-medium mb-2">{t('twa.rateWork')}</p>
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
                  &#8617; {t('twa.returnBtn')}
                </button>
                <button
                  onClick={handleAccept}
                  disabled={isSubmitting}
                  className="flex-1 bg-blue-600 text-white py-2 rounded-xl text-sm disabled:opacity-50"
                >
                  &#10003; {t('twa.acceptBtn')}
                </button>
              </div>
            </>
          ) : (
            <>
              <p className="font-medium mb-2">{t('twa.whyReturn')}</p>
              <textarea
                className="w-full border rounded-xl p-3 text-sm min-h-[80px] mb-3 focus:outline-none focus:border-blue-500"
                placeholder={t('twa.describeProblem')}
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
                  {t('common.back')}
                </button>
                <button
                  onClick={handleReturn}
                  disabled={!returnReason.trim() || isSubmitting}
                  className="flex-1 bg-red-500 text-white py-2 rounded-xl text-sm disabled:opacity-40"
                >
                  {t('common.send')}
                </button>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  )
}
