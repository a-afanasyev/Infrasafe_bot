import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useAuthStore } from './stores/authStore'
import LoginPage from './pages/LoginPage'
import DashboardLayout from './layouts/DashboardLayout'
import { isTWA } from './utils/isTWA'
import { ACCESS_MODULE_ROLES, ACCESS_MANAGER_ROLES, MATERIALS_MODULE_ROLES, RESOURCE_MODULE_ROLES } from './constants/roles'
import { lazy, Suspense, useEffect } from 'react'
import LoadingSpinner from './components/shared/LoadingSpinner'
import GlobalErrorBoundary from './components/shared/GlobalErrorBoundary'
import PageErrorBoundary from './components/shared/PageErrorBoundary'
import OfflineIndicator from './components/shared/OfflineIndicator'
import { Toaster } from './components/ui/sonner'

const TWAApp = lazy(() => import('./twa/App'))
// FE-042: the default dashboard route — lazy like the other pages so it leaves
// the entry chunk (already wrapped in <Suspense> below).
const KanbanPage = lazy(() => import('./pages/KanbanPage'))

// Lazy-load pages not yet implemented
const ShiftsPage = lazy(() => import('./pages/ShiftsPage'))
const EmployeesPage = lazy(() => import('./pages/EmployeesPage'))
const EmployeeDetailPage = lazy(() => import('./pages/EmployeeDetailPage'))
const TemplatesPage = lazy(() => import('./pages/TemplatesPage'))
const AnalyticsPage = lazy(() => import('./pages/AnalyticsPage'))
const AddressesPage = lazy(() => import('./pages/AddressesPage'))
const ResidentBoardPage = lazy(() => import('./pages/ResidentBoardPage'))
const BoardEditorPage = lazy(() => import('./pages/BoardEditorPage'))
const RegisterPage = lazy(() => import('./pages/RegisterPage'))
const FeedbackPage = lazy(() => import('./pages/FeedbackPage'))
// access_control §9.6: live-панель охраны (отдельный route group — гард ролей
// модуля доступа, не общий admin/manager дашборда).
const AccessControlPage = lazy(() => import('./pages/access/AccessControlPage'))
// access_control §6/§13.2: экраны менеджера (история проездов + база доступа).
// Гард — ACCESS_MANAGER_ROLES (manager/system_admin; оператор охраны не входит).
const AccessHistoryPage = lazy(() => import('./pages/access/AccessHistoryPage'))
const AccessDatabasePage = lazy(() => import('./pages/access/AccessDatabasePage'))
const AccessEquipmentPage = lazy(() => import('./pages/access/AccessEquipmentPage'))
// Складской учёт материалов (приход/расход по заявкам). Гард — MATERIALS_MODULE_ROLES.
const MaterialsPage = lazy(() => import('./pages/materials/MaterialsPage'))
// Нативный раздел «Учёт ресурсов УК» (портируемый модуль). DARK за build-флагом
// VITE_RESOURCES_ENABLED — пока партнёрский edge не проксирует resource-api.
const ResourceAccountingSection = lazy(() => import('./pages/ResourceAccountingSection'))

// DARK-гейт нативного раздела ресурсоучёта: раздел монтируется и показывается в
// меню только при VITE_RESOURCES_ENABLED=true (билд-арг). По умолчанию OFF.
const RESOURCES_ENABLED = import.meta.env.VITE_RESOURCES_ENABLED === 'true'

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
  const { isAuthenticated, user, hydrating } = useAuthStore()
  const location = useLocation()
  // Wait for the cold-start cookie probe before deciding — otherwise a fresh tab
  // with a valid shared cookie would be bounced to /login on the first paint.
  if (hydrating) return <LoadingSpinner />
  if (!isAuthenticated) {
    // Preserve the original deep-link so login returns the user to it (return-to).
    const next = encodeURIComponent(location.pathname + location.search)
    return <Navigate to={`/login?next=${next}`} replace />
  }
  if (allowedRoles && !user?.roles?.some((r: string) => allowedRoles.includes(r))) {
    return <Navigate to="/resident-board" replace />
  }
  return <>{children}</>
}

// Root entry: anonymous visitors land on the public board (УК main page),
// authenticated staff go to the dashboard, TWA users to the Mini App.
function RootRedirect() {
  const { isAuthenticated, hydrating } = useAuthStore()
  if (isTWA()) return <Navigate to="/twa" replace />
  if (hydrating) return <LoadingSpinner />
  if (isAuthenticated) return <Navigate to="/dashboard" replace />
  return <Navigate to="/resident-board" replace />
}

export default function App() {
  const bootstrap = useAuthStore((s) => s.bootstrap)
  // Recover a shared-cookie session on cold start (new tab / deep-link). Always
  // runs so `hydrating` is resolved even on TWA/public routes (a no-session probe
  // just 401s and clears the flag); the web guards depend on it being resolved.
  useEffect(() => {
    bootstrap()
  }, [bootstrap])

  return (
    <QueryClientProvider client={queryClient}>
      {/* FE-046: global offline banner (shared with TWA) */}
      <OfflineIndicator />
      <Toaster position="bottom-right" richColors />
      <GlobalErrorBoundary>
        <BrowserRouter basename={import.meta.env.BASE_URL}>
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
                <Route path="board-editor" element={<PageErrorBoundary><BoardEditorPage /></PageErrorBoundary>} />
                <Route path="feedback" element={<PageErrorBoundary><FeedbackPage /></PageErrorBoundary>} />
              </Route>

              {/* access_control §9.6: контроль доступа — отдельный route group с
                  гардом ролей модуля (manager/system_admin/security_operator).
                  Вынесен из основного /dashboard, т.к. тот пускает только
                  admin/manager, а security_operator/system_admin должны попадать
                  на панель охраны. executor/inspector/applicant — не видят. */}
              <Route path="/dashboard/access" element={<ProtectedRoute allowedRoles={[...ACCESS_MODULE_ROLES]}><DashboardLayout /></ProtectedRoute>}>
                <Route index element={<PageErrorBoundary><AccessControlPage /></PageErrorBoundary>} />
              </Route>

              {/* access_control §6/§13.2: экраны менеджера (история проездов +
                  база доступа). Отдельный route group — гард ACCESS_MANAGER_ROLES
                  (manager/system_admin), оператор охраны сюда не допускается. */}
              <Route path="/dashboard/access/history" element={<ProtectedRoute allowedRoles={[...ACCESS_MANAGER_ROLES]}><DashboardLayout /></ProtectedRoute>}>
                <Route index element={<PageErrorBoundary><AccessHistoryPage /></PageErrorBoundary>} />
              </Route>
              <Route path="/dashboard/access/database" element={<ProtectedRoute allowedRoles={[...ACCESS_MANAGER_ROLES]}><DashboardLayout /></ProtectedRoute>}>
                <Route index element={<PageErrorBoundary><AccessDatabasePage /></PageErrorBoundary>} />
              </Route>
              {/* access_control: «Оборудование» (зоны/въезды/камеры/шлагбаумы/
                  контроллеры). Гард — ACCESS_MANAGER_ROLES; камеры/шлагбаумы/
                  контроллеры внутри доступны только system_admin (гейтинг табов). */}
              <Route path="/dashboard/access/equipment" element={<ProtectedRoute allowedRoles={[...ACCESS_MANAGER_ROLES]}><DashboardLayout /></ProtectedRoute>}>
                <Route index element={<PageErrorBoundary><AccessEquipmentPage /></PageErrorBoundary>} />
              </Route>

              {/* Складской учёт материалов: номенклатура, остатки, журнал
                  операций, «на закуп». Гард — MATERIALS_MODULE_ROLES. */}
              <Route path="/dashboard/materials" element={<ProtectedRoute allowedRoles={[...MATERIALS_MODULE_ROLES]}><DashboardLayout /></ProtectedRoute>}>
                <Route index element={<PageErrorBoundary><MaterialsPage /></PageErrorBoundary>} />
              </Route>

              {/* Учёт ресурсов УК — нативный портируемый модуль (не iframe).
                  Splat-роут: внутренний <ResourceAccountingRoutes/> резолвит
                  подпути относительно basePath. Гард — RESOURCE_MODULE_ROLES.
                  DARK за VITE_RESOURCES_ENABLED (edge resource-api пока 404). */}
              {RESOURCES_ENABLED && (
                <Route path="/dashboard/resource-accounting" element={<ProtectedRoute allowedRoles={[...RESOURCE_MODULE_ROLES]}><DashboardLayout /></ProtectedRoute>}>
                  <Route path="*" element={<PageErrorBoundary><ResourceAccountingSection /></PageErrorBoundary>} />
                </Route>
              )}

              {/* Resident board - public standalone page (УК landing) */}
              <Route path="/resident-board" element={<PageErrorBoundary><ResidentBoardPage /></PageErrorBoundary>} />

              {/* Applicant registration - public Telegram Mini App page */}
              <Route path="/register" element={<PageErrorBoundary><RegisterPage /></PageErrorBoundary>} />

              {/* TWA — self-contained Mini App */}
              <Route path="/twa/*" element={<PageErrorBoundary><TWAApp /></PageErrorBoundary>} />

              <Route path="/" element={<RootRedirect />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </Suspense>
        </BrowserRouter>
      </GlobalErrorBoundary>
    </QueryClientProvider>
  )
}
