import { Routes, Route, Navigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useEffect } from 'react'
import { useTWAAuth } from './hooks/useTWAAuth'
import { useTelegramSDK } from './hooks/useTelegramSDK'
import { ApplicantTabs } from './components/BottomTabBar'
import { twaClient } from './twaClient'
import '../i18n'

// Pages
import HomePage from './pages/applicant/HomePage'
import RequestsPage from './pages/applicant/RequestsPage'
import CreatePage from './pages/applicant/CreatePage'
import AcceptancePage from './pages/applicant/AcceptancePage'
import ProfilePage from './pages/applicant/ProfilePage'
import RequestDetailPage from './pages/applicant/RequestDetailPage'

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
      <Routes>
        <Route path="/" element={<Navigate to="/twa/app" replace />} />
        <Route path="/app" element={<HomePage />} />
        <Route path="/app/requests" element={<RequestsPage />} />
        <Route path="/app/create" element={<CreatePage />} />
        <Route path="/app/acceptance" element={<AcceptancePage />} />
        <Route path="/app/profile" element={<ProfilePage />} />
        <Route path="/app/requests/:number" element={<RequestDetailPage />} />
        <Route path="*" element={<Navigate to="/twa/app" replace />} />
      </Routes>
      <ApplicantTabs />
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
