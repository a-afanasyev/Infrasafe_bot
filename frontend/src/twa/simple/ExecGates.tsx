import type { ReactNode } from 'react'
import { Navigate, useParams, useSearchParams } from 'react-router'
import { useTranslation } from 'react-i18next'
import TaskDetailPage from '../pages/executor/TaskDetailPage'
import { useSimpleMode } from './hooks/useSimpleMode'

function Loading() {
  const { t } = useTranslation()
  return (
    <div className="flex items-center justify-center min-h-screen text-gray-400 text-[16px]">
      {t('common.loading')}
    </div>
  )
}

/** /twa/exec: простой режим → /twa/s, иначе обычная панель. */
export function ExecHomeGate({ children }: { children: ReactNode }) {
  const { isLoading, simple } = useSimpleMode()
  if (isLoading) return <Loading />
  if (simple) return <Navigate to="/twa/s" replace />
  return <>{children}</>
}

/**
 * /twa/exec/tasks/:n[?action=done] — единственная ссылка бота на заявку;
 * куда вести, решает фронт (контракт маршрутов простого режима):
 *   simple  → /twa/s/task/:n  (action=done → /twa/s/task/:n/done)
 *   обычный → карточка        (action=done → отчёт /twa/exec/report/:n)
 */
export function ExecTaskEntry() {
  const { number = '' } = useParams()
  const [params] = useSearchParams()
  const { isLoading, simple } = useSimpleMode()
  const done = params.get('action') === 'done'
  if (isLoading) return <Loading />
  if (simple) return <Navigate to={`/twa/s/task/${encodeURIComponent(number)}${done ? '/done' : ''}`} replace />
  if (done) return <Navigate to={`/twa/exec/report/${encodeURIComponent(number)}`} replace />
  return <TaskDetailPage />
}
