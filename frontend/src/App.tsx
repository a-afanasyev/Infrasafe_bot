import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useAuthStore } from './stores/authStore'
import LoginPage from './pages/LoginPage'
import DashboardPage from './pages/DashboardPage'
import { isTWA } from './utils/isTWA'
import { lazy, Suspense } from 'react'

const TWAHomePage = lazy(() => import('./pages/twa/TWAHomePage'))
const TWACreatePage = lazy(() => import('./pages/twa/TWACreatePage'))
const TWARequestDetailPage = lazy(() => import('./pages/twa/TWARequestDetailPage'))

const queryClient = new QueryClient()

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated } = useAuthStore()
  if (!isAuthenticated) return <Navigate to="/login" replace />
  return <>{children}</>
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Suspense fallback={<div className="p-8 text-center text-gray-400">Loading...</div>}>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/dashboard" element={<ProtectedRoute><DashboardPage /></ProtectedRoute>} />

            {/* TWA routes */}
            <Route path="/twa" element={<TWAHomePage />} />
            <Route path="/twa/create" element={<TWACreatePage />} />
            <Route path="/twa/requests/:number" element={<TWARequestDetailPage />} />

            <Route path="/" element={<Navigate to={isTWA() ? '/twa' : '/dashboard'} replace />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Suspense>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
