import { useState, useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Phone } from 'lucide-react'
import KanbanBoard from '../components/kanban/KanbanBoard'
import CallCenterModal from '../components/callcenter/CallCenterModal'
import RequestDetailModal from '../components/kanban/RequestDetailModal'
import { useTopbar } from '../contexts/TopbarContext'
import { usePageTitle } from '../hooks/usePageTitle'
import { Button } from '@/components/ui/button'

export default function KanbanPage() {
  const { t } = useTranslation()
  usePageTitle(t('nav.requests'))
  const [callCenterOpen, setCallCenterOpen] = useState(false)
  const [selectedRequest, setSelectedRequest] = useState<string | null>(null)
  const [lastDeepLink, setLastDeepLink] = useState<string | null>(null)
  const [searchParams, setSearchParams] = useSearchParams()
  const { setActions, clearActions } = useTopbar()

  // Deep-link from InfraSafe admin panel ("Открыть в УК"): /dashboard?request=<номер>.
  // Runs only inside ProtectedRoute (admin|manager) — an unauthenticated or wrong-role
  // user is bounced to /login or /resident-board before KanbanPage mounts, so the link
  // never opens a request for them (the ?request= param is dropped on redirect).
  // Reopen context (reopen_sequence/related_request) is rendered from the request body —
  // we only need ?request= to know which modal to open.
  //
  // Adopt a freshly-arrived deep-link at render time (FE-034 pattern: adjust state when an
  // input changes, instead of setState-in-effect). lastDeepLink debounces it to a one-shot;
  // resetting it to null when the param clears lets the same number deep-link again later.
  const deepLinkRequest = searchParams.get('request')
  if (deepLinkRequest && deepLinkRequest !== lastDeepLink) {
    setLastDeepLink(deepLinkRequest)
    setSelectedRequest(deepLinkRequest)
  } else if (!deepLinkRequest && lastDeepLink !== null) {
    setLastDeepLink(null)
  }

  // Strip the deep-link query once consumed — pure external side-effect (URL/history only),
  // so a refresh/close doesn't re-open and the URL stays clean.
  useEffect(() => {
    if (!deepLinkRequest) return
    const next = new URLSearchParams(searchParams)
    next.delete('request')
    next.delete('reopen_sequence')
    next.delete('related_request')
    next.delete('reopen_chain_id')
    setSearchParams(next, { replace: true })
  }, [deepLinkRequest, searchParams, setSearchParams])

  useEffect(() => {
    setActions(
      <Button
        onClick={() => setCallCenterOpen(true)}
        size="sm"
      >
        <Phone size={14} />
        {t('kanban.createByCall')}
      </Button>
    )
    return clearActions
    // FE-08: include reactive deps so the button label re-renders on language
    // change (setActions/clearActions are stable useCallback refs).
  }, [t, setActions, clearActions])

  return (
    <div className="p-6 h-full">
      <KanbanBoard onCardClick={setSelectedRequest} />
      <CallCenterModal isOpen={callCenterOpen} onClose={() => setCallCenterOpen(false)} />
      <RequestDetailModal
        requestNumber={selectedRequest}
        onClose={() => setSelectedRequest(null)}
        onOpenRelated={setSelectedRequest}
      />
    </div>
  )
}
