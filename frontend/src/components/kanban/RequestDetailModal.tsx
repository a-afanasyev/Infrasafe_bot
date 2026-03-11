import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiClient } from '../../api/client'

const URGENCY_COLOR: Record<string, string> = {
  'Обычная': 'bg-green-100 text-green-700',
  'Средняя': 'bg-yellow-100 text-yellow-700',
  'Срочная': 'bg-orange-100 text-orange-700',
  'Критическая': 'bg-red-100 text-red-700',
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

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50" onClick={onClose}>
      <div
        className="bg-white rounded-2xl w-full max-w-lg max-h-[85vh] shadow-xl flex flex-col"
        onClick={e => e.stopPropagation()}
      >
        {!request ? (
          <div className="p-6 text-gray-400 text-center">Загрузка...</div>
        ) : (
          <>
            {/* Header */}
            <div className="p-4 border-b flex justify-between items-start shrink-0">
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-mono text-xs text-gray-500">{request.request_number}</span>
                  <span className="text-sm">{SOURCE_ICON[request.source ?? ''] ?? ''}</span>
                </div>
                <h2 className="font-bold mt-1">{request.category}</h2>
              </div>
              <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-xl leading-none">&times;</button>
            </div>

            {/* Body */}
            <div className="p-4 overflow-y-auto flex-1 space-y-4">
              {/* Badges */}
              <div className="flex gap-2 flex-wrap">
                <span className="text-xs px-2 py-1 rounded-full bg-blue-100 text-blue-700">{request.status}</span>
                {request.urgency && (
                  <span className={`text-xs px-2 py-1 rounded-full ${URGENCY_COLOR[request.urgency] ?? 'bg-gray-100 text-gray-600'}`}>
                    {request.urgency}
                  </span>
                )}
                {request.manager_confirmed && (
                  <span className="text-xs px-2 py-1 rounded-full bg-emerald-100 text-emerald-700">✓ Подтверждено</span>
                )}
              </div>

              {/* Description */}
              {request.description && (
                <p className="text-sm text-gray-700">{request.description}</p>
              )}

              {/* Details */}
              <div className="text-xs text-gray-500 space-y-1">
                <div>Создана: {new Date(request.created_at).toLocaleString('ru')}</div>
                {request.executor_name && (
                  <div>Исполнитель: <span className="font-medium text-gray-700">{request.executor_name}</span></div>
                )}
                {request.address && <div>Адрес: {request.address}</div>}
              </div>

              {/* Contextual info blocks */}
              {request.requested_materials && (
                <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 text-sm">
                  <span className="font-semibold text-amber-700">Закуп: </span>
                  <span className="text-amber-800">{request.requested_materials}</span>
                </div>
              )}
              {request.notes && (
                <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 text-sm">
                  <span className="font-semibold text-blue-700">Уточнение: </span>
                  <span className="text-blue-800">{request.notes}</span>
                </div>
              )}
              {request.completion_report && (
                <div className="bg-green-50 border border-green-200 rounded-lg p-3 text-sm">
                  <span className="font-semibold text-green-700">Отчёт: </span>
                  <span className="text-green-800">{request.completion_report}</span>
                </div>
              )}
              {request.return_reason && (
                <div className="bg-red-50 border border-red-200 rounded-lg p-3 text-sm">
                  <span className="font-semibold text-red-700">Возврат: </span>
                  <span className="text-red-800">{request.return_reason}</span>
                </div>
              )}

              {/* Manager confirmation (Выполнена → Исполнено) */}
              {request.status === 'Выполнена' && (
                <div className="border border-gray-200 rounded-xl p-3 bg-gray-50">
                  {!showConfirmSection ? (
                    <button
                      onClick={() => setShowConfirmSection(true)}
                      className="w-full bg-emerald-600 text-white py-2 rounded-lg text-sm font-medium hover:bg-emerald-700"
                    >
                      ✓ Подтвердить и отправить жителю
                    </button>
                  ) : (
                    <div className="space-y-2">
                      <p className="text-xs text-gray-600">Комментарий (необязательно):</p>
                      <textarea
                        className="w-full border rounded-lg p-2 text-sm min-h-[60px] focus:outline-none focus:border-emerald-500"
                        placeholder="Всё выполнено качественно"
                        value={confirmNote}
                        onChange={e => setConfirmNote(e.target.value)}
                      />
                      <div className="flex gap-2">
                        <button
                          onClick={() => setShowConfirmSection(false)}
                          className="flex-1 border py-1.5 rounded-lg text-sm text-gray-600 hover:bg-gray-50"
                        >
                          Отмена
                        </button>
                        <button
                          onClick={() => updateRequest.mutate({
                            status: 'Исполнено',
                            manager_confirmed: true,
                            ...(confirmNote ? { manager_confirmation_notes: confirmNote } : {}),
                          })}
                          disabled={updateRequest.isPending}
                          className="flex-1 bg-emerald-600 text-white py-1.5 rounded-lg text-sm font-medium disabled:opacity-50"
                        >
                          {updateRequest.isPending ? 'Сохраняю...' : 'Подтвердить'}
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* Comments history */}
              {comments && comments.length > 0 && (
                <div>
                  <h3 className="text-xs font-semibold text-gray-500 uppercase mb-2">История</h3>
                  <div className="space-y-2">
                    {comments.map((c: {
                      id: number
                      comment_text: string
                      is_internal: boolean
                      created_at: string
                    }) => (
                      <div
                        key={c.id}
                        className={`rounded-xl p-3 border text-sm ${
                          c.is_internal ? 'bg-amber-50 border-amber-100' : 'bg-gray-50'
                        }`}
                      >
                        <p>{c.comment_text}</p>
                        <span className="text-xs text-gray-400">{new Date(c.created_at).toLocaleString('ru')}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Add comment */}
              <div className="space-y-1">
                <h3 className="text-xs font-semibold text-gray-500 uppercase">Заметка менеджера</h3>
                <div className="flex gap-2">
                  <input
                    className="flex-1 border rounded-xl px-3 py-2 text-sm focus:outline-none focus:border-blue-500"
                    placeholder="Добавить заметку..."
                    value={comment}
                    onChange={e => setComment(e.target.value)}
                    onKeyDown={e => e.key === 'Enter' && comment.trim() && postComment.mutate(comment)}
                  />
                  <button
                    onClick={() => postComment.mutate(comment)}
                    disabled={!comment.trim() || postComment.isPending}
                    className="bg-blue-600 text-white px-3 py-2 rounded-xl text-sm disabled:opacity-40"
                  >
                    ↑
                  </button>
                </div>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
