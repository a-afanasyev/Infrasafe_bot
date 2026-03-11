import { useQuery } from '@tanstack/react-query'
import { apiClient } from '../../api/client'
import { useTWAAuth } from '../../hooks/useTWAAuth'
import { useNavigate } from 'react-router-dom'

export default function TWAHomePage() {
  useTWAAuth()
  const navigate = useNavigate()

  const { data: requests } = useQuery({
    queryKey: ['my-requests'],
    queryFn: () => apiClient.get('/api/v2/requests?limit=10').then(r => r.data),
  })

  const activeRequests = (requests ?? []).filter((r: { status: string }) =>
    !['Принято', 'Отменена'].includes(r.status)
  )

  return (
    <div className="p-4 pb-20 bg-gray-50 min-h-screen">
      <h1 className="text-xl font-bold mb-4">Мои заявки</h1>

      {activeRequests.length === 0 && (
        <p className="text-gray-400 text-center py-8">Нет активных заявок</p>
      )}

      {activeRequests.map((req: { request_number: string; status: string; category: string; description: string }) => (
        <div key={req.request_number} onClick={() => navigate(`/twa/requests/${req.request_number}`)}
          className="bg-white border rounded-xl p-3 mb-2 cursor-pointer active:bg-gray-50">
          <div className="flex justify-between">
            <span className="font-mono text-xs text-gray-500">{req.request_number}</span>
            <span className={`text-xs px-2 py-0.5 rounded-full ${req.status === 'Выполнена' ? 'bg-orange-100 text-orange-700' : 'bg-blue-100 text-blue-700'}`}>
              {req.status}
            </span>
          </div>
          <p className="text-sm font-medium mt-1">{req.category}</p>
          <p className="text-xs text-gray-500 mt-0.5 line-clamp-1">{req.description}</p>
        </div>
      ))}

      <button onClick={() => navigate('/twa/create')}
        className="fixed bottom-4 left-4 right-4 bg-blue-600 text-white py-3 rounded-xl font-medium text-center shadow-lg">
        + Создать заявку
      </button>
    </div>
  )
}
