import { useState, useEffect } from 'react'
import { Phone } from 'lucide-react'
import KanbanBoard from '../components/kanban/KanbanBoard'
import CallCenterModal from '../components/callcenter/CallCenterModal'
import RequestDetailModal from '../components/kanban/RequestDetailModal'
import { useTopbar } from '../contexts/TopbarContext'

export default function KanbanPage() {
  const [callCenterOpen, setCallCenterOpen] = useState(false)
  const [selectedRequest, setSelectedRequest] = useState<string | null>(null)
  const { setActions, clearActions } = useTopbar()

  useEffect(() => {
    setActions(
      <button
        onClick={() => setCallCenterOpen(true)}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '6px',
          background: 'var(--accent)',
          color: '#000',
          border: 'none',
          borderRadius: 'var(--radius-sm)',
          padding: '8px 14px',
          fontSize: '13px',
          fontWeight: 600,
          cursor: 'pointer',
          fontFamily: 'var(--font-body)',
        }}
      >
        <Phone size={14} />
        Создать по звонку
      </button>
    )
    return clearActions
  }, [])

  return (
    <div style={{ padding: '24px', height: '100%' }}>
      <KanbanBoard onCardClick={setSelectedRequest} />
      <CallCenterModal isOpen={callCenterOpen} onClose={() => setCallCenterOpen(false)} />
      <RequestDetailModal requestNumber={selectedRequest} onClose={() => setSelectedRequest(null)} />
    </div>
  )
}
