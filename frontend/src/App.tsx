import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useAuthStore } from './stores/authStore'
import LoginPage from './pages/LoginPage'
import DashboardLayout from './layouts/DashboardLayout'
import KanbanPage from './pages/KanbanPage'
import { isTWA } from './utils/isTWA'
import { lazy, Suspense } from 'react'
import LoadingSpinner from './components/shared/LoadingSpinner'

const TWAHomePage = lazy(() => import('./pages/twa/TWAHomePage'))
const TWACreatePage = lazy(() => import('./pages/twa/TWACreatePage'))
const TWARequestDetailPage = lazy(() => import('./pages/twa/TWARequestDetailPage'))

// Lazy-load pages not yet implemented
const ShiftsPage = lazy(() => import('./pages/ShiftsPage'))
const EmployeesPage = lazy(() => import('./pages/EmployeesPage'))
const TemplatesPage = lazy(() => import('./pages/TemplatesPage'))
const AnalyticsPage = lazy(() => import('./pages/AnalyticsPage'))

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
        <Suspense fallback={<LoadingSpinner />}>
          <Routes>
            <Route path="/login" element={<LoginPage />} />

            <Route path="/dashboard" element={<ProtectedRoute><DashboardLayout /></ProtectedRoute>}>
              <Route index element={<KanbanPage />} />
              <Route path="analytics" element={<AnalyticsPage />} />
              <Route path="shifts" element={<ShiftsPage />} />
              <Route path="employees" element={<EmployeesPage />} />
              <Route path="templates" element={<TemplatesPage />} />
            </Route>

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
