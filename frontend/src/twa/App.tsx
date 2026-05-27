import { Routes, Route, Navigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useEffect } from 'react'
import { useTWAAuth } from './hooks/useTWAAuth'
import { useTelegramSDK } from './hooks/useTelegramSDK'
import { ApplicantTabs } from './components/BottomTabBar'
import { ExecutorTabs } from './components/ExecutorTabs'
import { twaClient } from './twaClient'
import OfflineIndicator from './components/OfflineIndicator'
import RoleGuard from './components/RoleGuard'
import { Toaster } from '../components/ui/sonner'
import '../i18n'

// Applicant pages
import HomePage from './pages/applicant/HomePage'
import RequestsPage from './pages/applicant/RequestsPage'
import CreatePage from './pages/applicant/CreatePage'
import AcceptancePage from './pages/applicant/AcceptancePage'
import ProfilePage from './pages/applicant/ProfilePage'
import RequestDetailPage from './pages/applicant/RequestDetailPage'

// Executor pages
import TasksPage from './pages/executor/TasksPage'
import ShiftPage from './pages/executor/ShiftPage'
import PurchasePage from './pages/executor/PurchasePage'
import ArchivePage from './pages/executor/ArchivePage'
import ExecutorProfilePage from './pages/executor/ProfilePage'
import TaskDetailPage from './pages/executor/TaskDetailPage'
import MyShiftsPage from './pages/executor/MyShiftsPage'
import CompletionReport from './pages/executor/CompletionReport'

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false, staleTime: 30_000 } },
})

function TWAContent() {
  const { accessToken, isLoading, isAuthenticated } = useTWAAuth()

  // Set auth header for TWA-specific client (not shared apiClient)
  useEffect(() => {
    if (accessToken) {
      twaClient.defaults.headers.common['Authorization'] = `Bearer ${accessToken}`
    }
  }, [accessToken])

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-gray-50 dark:bg-gray-950">
        <p className="text-gray-400 text-[14px]">Loading...</p>
      </div>
    )
  }

  if (!isAuthenticated) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen bg-gray-50 dark:bg-gray-950 p-6 text-center">
        <p className="text-[40px] mb-3">🔒</p>
        <p className="text-gray-500 text-[14px]">Open via Telegram bot to authenticate</p>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-950 text-gray-900 dark:text-gray-100">
      <OfflineIndicator />
      <Toaster position="top-center" richColors closeButton />
      <Routes>
        <Route path="/" element={<Navigate to="/twa/app" replace />} />

        {/* Applicant routes */}
        <Route path="/app" element={<><HomePage /><ApplicantTabs /></>} />
        <Route path="/app/requests" element={<><RequestsPage /><ApplicantTabs /></>} />
        <Route path="/app/create" element={<><CreatePage /><ApplicantTabs /></>} />
        <Route path="/app/acceptance" element={<><AcceptancePage /><ApplicantTabs /></>} />
        <Route path="/app/profile" element={<><ProfilePage /><ApplicantTabs /></>} />
        <Route path="/app/requests/:number" element={<RequestDetailPage />} />

        {/* Executor routes — wrapped in RoleGuard (TWA-12) so an applicant
            opening /twa/exec/* gets sent back to /twa/app rather than seeing
            an empty executor UI with 403s in the network panel. */}
        <Route path="/exec" element={<RoleGuard required="executor"><TasksPage /><ExecutorTabs /></RoleGuard>} />
        <Route path="/exec/shift" element={<RoleGuard required="executor"><ShiftPage /><ExecutorTabs /></RoleGuard>} />
        <Route path="/exec/purchase" element={<RoleGuard required="executor"><PurchasePage /><ExecutorTabs /></RoleGuard>} />
        <Route path="/exec/archive" element={<RoleGuard required="executor"><ArchivePage /><ExecutorTabs /></RoleGuard>} />
        <Route path="/exec/profile" element={<RoleGuard required="executor"><ExecutorProfilePage /><ExecutorTabs /></RoleGuard>} />
        <Route path="/exec/tasks/:number" element={<RoleGuard required="executor"><TaskDetailPage /></RoleGuard>} />
        <Route path="/exec/shifts" element={<RoleGuard required="executor"><MyShiftsPage /></RoleGuard>} />
        <Route path="/exec/report/:number" element={<RoleGuard required="executor"><CompletionReport /></RoleGuard>} />

        <Route path="*" element={<Navigate to="/twa/app" replace />} />
      </Routes>
    </div>
  )
}

export default function TWAApp() {
  const { colorScheme } = useTelegramSDK()

  return (
    <div className={colorScheme === 'dark' ? 'dark' : ''}>
      <QueryClientProvider client={queryClient}>
        <TWAContent />
      </QueryClientProvider>
    </div>
  )
}
