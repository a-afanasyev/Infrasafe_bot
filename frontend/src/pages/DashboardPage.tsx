import { useState } from 'react'
import KanbanBoard from '../components/kanban/KanbanBoard'
import CallCenterModal from '../components/callcenter/CallCenterModal'
import RequestDetailModal from '../components/kanban/RequestDetailModal'

export default function DashboardPage() {
  const [callCenterOpen, setCallCenterOpen] = useState(false)
  const [selectedRequest, setSelectedRequest] = useState<string | null>(null)

  return (
    <div className="flex flex-col h-screen">
      <div className="flex items-center gap-3 px-4 py-3 border-b bg-white">
        <h1 className="font-bold text-lg">UK Management</h1>
        <nav className="flex gap-2 ml-4">
          <a href="/dashboard" className="text-sm font-medium text-blue-600">Канбан</a>
          <a href="/requests" className="text-sm text-gray-500 hover:text-gray-800">Заявки</a>
          <a href="/staff" className="text-sm text-gray-500 hover:text-gray-800">Сотрудники</a>
          <a href="/reports" className="text-sm text-gray-500 hover:text-gray-800">Отчёты</a>
        </nav>
        <div className="ml-auto flex gap-2">
          <button onClick={() => setCallCenterOpen(true)} className="bg-green-600 text-white px-3 py-1.5 rounded-lg text-sm font-medium">
            Создать по звонку
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-hidden p-4">
        <KanbanBoard onCardClick={setSelectedRequest} />
      </div>

      <CallCenterModal isOpen={callCenterOpen} onClose={() => setCallCenterOpen(false)} />
      <RequestDetailModal requestNumber={selectedRequest} onClose={() => setSelectedRequest(null)} />
    </div>
  )
}
