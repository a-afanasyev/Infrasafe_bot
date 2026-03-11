import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient } from '../../api/client'
import { useTWAAuth } from '../../hooks/useTWAAuth'

const STATUS_ORDER = ['Новая', 'В работе', 'Закуп', 'Уточнение', 'Выполнена', 'Исполнено', 'Принято']

export default function TWARequestDetailPage() {
  useTWAAuth()
  const { number } = useParams<{ number: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [message, setMessage] = useState('')
  const [rating, setRating] = useState(0)
  const [sending, setSending] = useState(false)

  const { data: request } = useQuery({
    queryKey: ['request', number],
    queryFn: () => apiClient.get(`/api/v2/requests/${number}`).then(r => r.data),
  })

  const { data: comments } = useQuery({
    queryKey: ['comments', number],
    queryFn: () => apiClient.get(`/api/v2/requests/${number}/comments`).then(r => r.data),
  })

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
    await apiClient.patch(`/api/v2/requests/${number}`, { status: 'Принято' })
    queryClient.invalidateQueries({ queryKey: ['request', number] })
    navigate('/twa')
  }

  const handleReturn = async () => {
    await apiClient.patch(`/api/v2/requests/${number}`, { status: 'В работе' })
    queryClient.invalidateQueries({ queryKey: ['request', number] })
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
        <div className="flex gap-1 min-w-max">
          {STATUS_ORDER.map((s, i) => (
            <div key={s} className={`text-xs px-2 py-1 rounded ${i <= currentIdx ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-400'}`}>
              {s}
            </div>
          ))}
        </div>
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
          <p className="font-medium mb-2">Оцените работу</p>
          <div className="flex gap-2 mb-3">
            {[1,2,3,4,5].map(n => (
              <button key={n} onClick={() => setRating(n)}
                className={`text-2xl ${n <= rating ? 'text-yellow-400' : 'text-gray-300'}`}>
                &#9733;
              </button>
            ))}
          </div>
          <div className="flex gap-2">
            <button onClick={handleReturn} className="flex-1 border py-2 rounded-xl text-sm">
              &#8617; Вернуть
            </button>
            <button onClick={handleAccept} className="flex-1 bg-blue-600 text-white py-2 rounded-xl text-sm">
              &#10003; Принять
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
