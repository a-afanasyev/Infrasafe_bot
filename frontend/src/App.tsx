import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useAuthStore } from './stores/authStore'
import LoginPage from './pages/LoginPage'
import DashboardLayout from './layouts/DashboardLayout'
import KanbanPage from './pages/KanbanPage'
import { isTWA } from './utils/isTWA'
import { lazy, Suspense } from 'react'
import LoadingSpinner from './components/shared/LoadingSpinner'
import GlobalErrorBoundary from './components/shared/GlobalErrorBoundary'
import PageErrorBoundary from './components/shared/PageErrorBoundary'
import { Toaster } from './components/ui/sonner'

const TWAApp = lazy(() => import('./twa/App'))

// Lazy-load pages not yet implemented
const ShiftsPage = lazy(() => import('./pages/ShiftsPage'))
const EmployeesPage = lazy(() => import('./pages/EmployeesPage'))
const EmployeeDetailPage = lazy(() => import('./pages/EmployeeDetailPage'))
const TemplatesPage = lazy(() => import('./pages/TemplatesPage'))
const AnalyticsPage = lazy(() => import('./pages/AnalyticsPage'))
const AddressesPage = lazy(() => import('./pages/AddressesPage'))
const ResidentBoardPage = lazy(() => import('./pages/ResidentBoardPage'))

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: false,
    },
  },
})

interface ProtectedRouteProps {
  children: React.ReactNode
  allowedRoles?: string[]
}

function ProtectedRoute({ children, allowedRoles }: ProtectedRouteProps) {
  const { isAuthenticated, user } = useAuthStore()
  if (!isAuthenticated) return <Navigate to="/login" replace />
  if (allowedRoles && !user?.roles?.some((r: string) => allowedRoles.includes(r))) {
    return <Navigate to="/resident-board" replace />
  }
  return <>{children}</>
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <Toaster position="bottom-right" richColors />
      <GlobalErrorBoundary>
        <BrowserRouter>
          <Suspense fallback={<LoadingSpinner />}>
            <Routes>
              <Route path="/login" element={<LoginPage />} />

              <Route path="/dashboard" element={<ProtectedRoute allowedRoles={['admin', 'manager']}><DashboardLayout /></ProtectedRoute>}>
                <Route index element={<PageErrorBoundary><KanbanPage /></PageErrorBoundary>} />
                <Route path="analytics" element={<PageErrorBoundary><AnalyticsPage /></PageErrorBoundary>} />
                <Route path="shifts" element={<PageErrorBoundary><ShiftsPage /></PageErrorBoundary>} />
                <Route path="employees" element={<PageErrorBoundary><EmployeesPage /></PageErrorBoundary>} />
                <Route path="employees/:id" element={<PageErrorBoundary><EmployeeDetailPage /></PageErrorBoundary>} />
                <Route path="templates" element={<PageErrorBoundary><TemplatesPage /></PageErrorBoundary>} />
                <Route path="addresses" element={<PageErrorBoundary><AddressesPage /></PageErrorBoundary>} />
              </Route>

              {/* Resident board - standalone page */}
              <Route path="/resident-board" element={<ProtectedRoute><PageErrorBoundary><ResidentBoardPage /></PageErrorBoundary></ProtectedRoute>} />

              {/* TWA — self-contained Mini App */}
              <Route path="/twa/*" element={<PageErrorBoundary><TWAApp /></PageErrorBoundary>} />

              <Route path="/" element={<Navigate to={isTWA() ? '/twa' : '/dashboard'} replace />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </Suspense>
        </BrowserRouter>
      </GlobalErrorBoundary>
    </QueryClientProvider>
  )
}
