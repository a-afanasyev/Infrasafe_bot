import { Navigate, Outlet, useLocation } from 'react-router'
import { isLangChosen } from './langFlag'
import { ConnectionBar } from './components/Chrome'
import { CompletionQueueProvider } from './queue/CompletionQueue'

/**
 * Каркас простого режима (/twa/s/*): очередь «Готово» (досылается при
 * открытии), полоса связи, первый вход — через выбор языка.
 */
export default function SimpleShell() {
  const { pathname, search } = useLocation()
  if (!isLangChosen()) {
    const next = encodeURIComponent(pathname + search)
    return <Navigate to={`/twa/s/lang?next=${next}`} replace />
  }
  return (
    <CompletionQueueProvider>
      <div className="min-h-screen bg-gray-100 dark:bg-gray-950 text-gray-900 dark:text-gray-50 text-[18px]">
        <ConnectionBar />
        <Outlet />
      </div>
    </CompletionQueueProvider>
  )
}
