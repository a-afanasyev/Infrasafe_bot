import { useQuery } from '@tanstack/react-query'
import { apiClient } from '../../api/client'

const URGENCY_COLOR: Record<string, string> = {
  'Обычная': 'bg-green-100 text-green-700',
  'Средняя': 'bg-yellow-100 text-yellow-700',
  'Срочная': 'bg-orange-100 text-orange-700',
  'Критическая': 'bg-red-100 text-red-700',
}

const SOURCE_ICON: Record<string, string> = {
  bot: '\u{1F916}',
  twa: '\u{1F4F1}',
  web: '\u{1F310}',
  call_center: '\u{1F4DE}',
}

interface Props {
  requestNumber: string | null
  onClose: () => void
}

export default function RequestDetailModal({ requestNumber, onClose }: Props) {
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

  if (!requestNumber) return null

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50" onClick={onClose}>
      <div className="bg-white rounded-2xl w-full max-w-lg max-h-[80vh] shadow-xl flex flex-col" onClick={e => e.stopPropagation()}>
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
            <div className="p-4 overflow-y-auto flex-1">
              {/* Badges */}
              <div className="flex gap-2 flex-wrap mb-3">
                <span className="text-xs px-2 py-1 rounded-full bg-blue-100 text-blue-700">{request.status}</span>
                {request.urgency && (
                  <span className={`text-xs px-2 py-1 rounded-full ${URGENCY_COLOR[request.urgency] ?? 'bg-gray-100 text-gray-600'}`}>
                    {request.urgency}
                  </span>
                )}
              </div>

              {/* Description */}
              {request.description && (
                <p className="text-sm text-gray-700 mb-3">{request.description}</p>
              )}

              {/* Details */}
              <div className="text-xs text-gray-500 space-y-1 mb-4">
                <div>Создана: {new Date(request.created_at).toLocaleString('ru')}</div>
                {request.executor_name && <div>Исполнитель: {request.executor_name}</div>}
                {request.address && <div>Адрес: {request.address}</div>}
              </div>

              {/* Comments */}
              {comments && comments.length > 0 && (
                <div>
                  <h3 className="text-xs font-semibold text-gray-500 uppercase mb-2">Комментарии</h3>
                  <div className="space-y-2">
                    {comments.map((c: { id: number; comment_text: string; created_at: string }) => (
                      <div key={c.id} className="bg-gray-50 rounded-xl p-3 border">
                        <p className="text-sm">{c.comment_text}</p>
                        <span className="text-xs text-gray-400">{new Date(c.created_at).toLocaleString('ru')}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  )
}
