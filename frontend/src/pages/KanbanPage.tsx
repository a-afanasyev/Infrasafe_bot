import { useState, useEffect } from 'react'
import { Phone } from 'lucide-react'
import KanbanBoard from '../components/kanban/KanbanBoard'
import CallCenterModal from '../components/callcenter/CallCenterModal'
import RequestDetailModal from '../components/kanban/RequestDetailModal'
import { useTopbar } from '../contexts/TopbarContext'
import { usePageTitle } from '../hooks/usePageTitle'
import { Button } from '@/components/ui/button'

export default function KanbanPage() {
  usePageTitle('Заявки')
  const [callCenterOpen, setCallCenterOpen] = useState(false)
  const [selectedRequest, setSelectedRequest] = useState<string | null>(null)
  const { setActions, clearActions } = useTopbar()

  useEffect(() => {
    setActions(
      <Button
        onClick={() => setCallCenterOpen(true)}
        size="sm"
      >
        <Phone size={14} />
        Создать по звонку
      </Button>
    )
    return clearActions
  }, [])

  return (
    <div className="p-6 h-full">
      <KanbanBoard onCardClick={setSelectedRequest} />
      <CallCenterModal isOpen={callCenterOpen} onClose={() => setCallCenterOpen(false)} />
      <RequestDetailModal requestNumber={selectedRequest} onClose={() => setSelectedRequest(null)} />
    </div>
  )
}
