import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router'
import { QueryClientProvider } from '@tanstack/react-query'
import { queryClient } from './api/queryClient'
import { useAuthStore } from './stores/authStore'
import LoginPage from './pages/LoginPage'
import DashboardLayout from './layouts/DashboardLayout'
import { isTWA } from './utils/isTWA'
import { hasAction, type ActionKey } from './authz/actions'
import { lazy, Suspense, useEffect } from 'react'
import LoadingSpinner from './components/shared/LoadingSpinner'
import GlobalErrorBoundary from './components/shared/GlobalErrorBoundary'
import { DisplayTzProvider } from './contexts/DisplayTzProvider'
import PageErrorBoundary from './components/shared/PageErrorBoundary'
import OfflineIndicator from './components/shared/OfflineIndicator'
import RootToaster from './components/shared/RootToaster'

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
// Администрирование жителей: список/карточка. Пункт меню виден только
// по действию residents.manage (NAV_ENTRIES) — API гейтит то же действие.
const ResidentsPage = lazy(() => import('./pages/ResidentsPage'))
// Group Intake: реестр мониторимых ТГ-групп. Пункт меню виден только manager
// (действие group_intake.manage в NAV_ENTRIES) — API гейтит то же действие.
const GroupsPage = lazy(() => import('./pages/GroupsPage'))
const RolesPage = lazy(() => import('./pages/RolesPage'))
const ResidentDetailPage = lazy(() => import('./pages/ResidentDetailPage'))
const ResidentBoardPage = lazy(() => import('./pages/ResidentBoardPage'))
const ResidentHomePage = lazy(() => import('./pages/ResidentHomePage'))
const BoardEditorPage = lazy(() => import('./pages/BoardEditorPage'))
const RegisterPage = lazy(() => import('./pages/RegisterPage'))
const FeedbackPage = lazy(() => import('./pages/FeedbackPage'))
// access_control §9.6: live-панель охраны (отдельный route group — гард ролей
// модуля доступа, не общий admin/manager дашборда).
const AccessControlPage = lazy(() => import('./pages/access/AccessControlPage'))
// access_control §6/§13.2: экраны менеджера (история проездов + база доступа).
// Гард — действие access.registry.manage (оператор охраны не входит).
const AccessHistoryPage = lazy(() => import('./pages/access/AccessHistoryPage'))
const AccessDatabasePage = lazy(() => import('./pages/access/AccessDatabasePage'))
const AccessEquipmentPage = lazy(() => import('./pages/access/AccessEquipmentPage'))
// Складской учёт материалов (приход/расход по заявкам). Гард — materials.manage.
const PaymentControlPage = lazy(() => import('./pages/PaymentControlPage'))
const MaterialsPage = lazy(() => import('./pages/materials/MaterialsPage'))
// Нативный раздел «Учёт ресурсов УК» (портируемый модуль). DARK за build-флагом
// VITE_RESOURCES_ENABLED — пока партнёрский edge не проксирует resource-api.
const ResourceAccountingSection = lazy(() => import('./pages/ResourceAccountingSection'))

// DARK-гейт нативного раздела ресурсоучёта: раздел монтируется и показывается в
// меню только при VITE_RESOURCES_ENABLED=true (билд-арг). По умолчанию OFF.
const RESOURCES_ENABLED = import.meta.env.VITE_RESOURCES_ENABLED === 'true'

// Визуальные отчёты «до/после» (work-reports): менеджерская очередь модерации
// + публичный архив. DARK за VITE_WORK_REPORTS_ENABLED, по умолчанию OFF.
const WorkReportsPage = lazy(() => import('./pages/WorkReportsPage'))
const WorkReportsArchivePage = lazy(() => import('./pages/WorkReportsArchivePage'))
const WorkReportDetailPage = lazy(() => import('./pages/WorkReportDetailPage'))
const WORK_REPORTS_ENABLED = import.meta.env.VITE_WORK_REPORTS_ENABLED === 'true'

// Модуль «Лифты»: реестр, карточка, форма, календарь, конфиг. DARK за
// VITE_ELEVATORS_ENABLED (согласованно с backend ELEVATORS_ENABLED → 404).
const ElevatorsPage = lazy(() => import('./pages/elevators/ElevatorsPage'))
const ElevatorDetailPage = lazy(() => import('./pages/elevators/ElevatorDetailPage'))
const ElevatorFormPage = lazy(() => import('./pages/elevators/ElevatorFormPage'))
const ElevatorsCalendarPage = lazy(() => import('./pages/elevators/ElevatorsCalendarPage'))
const ElevatorsConfigPage = lazy(() => import('./pages/elevators/ElevatorsConfigPage'))
// Публичная страница «Лифты» (T17, Р17) — полный список к сводке на табло.
const ResidentElevatorsPage = lazy(() => import('./pages/ResidentElevatorsPage'))
const ELEVATORS_ENABLED = import.meta.env.VITE_ELEVATORS_ENABLED === 'true'

// Мониторинг отключений (очередь новостей + настройки). DARK за
// VITE_NEWS_WATCH_ENABLED (согласованно с backend NEWS_WATCH_ENABLED → 404).
const NewsWatchPage = lazy(() => import('./pages/NewsWatchPage'))
const NEWS_WATCH_ENABLED = import.meta.env.VITE_NEWS_WATCH_ENABLED === 'true'


interface ProtectedRouteProps {
  children: React.ReactNode
  /** Действие из каталога RBAC; без него — достаточно войти. Решает сервер. */
  action?: ActionKey
}

function ProtectedRoute({ children, action }: ProtectedRouteProps) {
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
  if (action && !hasAction(user?.actions, action)) {
    return <Navigate to="/home" replace />
  }
  return <>{children}</>
}

// Раздел дашборда по своему действию: общий гейт /dashboard — только вход
// (dashboard.use), а инженер, например, видит доску, но не персонал и смены.
// Без действия — на доску, а не на /home: человек в дашборде остаётся.
function ActionRoute({ children, action }: { children: React.ReactNode; action: ActionKey }) {
  const user = useAuthStore((s) => s.user)
  if (!hasAction(user?.actions, action)) return <Navigate to="/dashboard" replace />
  return <>{children}</>
}

// Root entry: anonymous visitors land on the resident home page (УК main page;
// the lobby-screen board stays at /resident-board),
// authenticated staff go to the dashboard, TWA users to the Mini App.
export function RootRedirect() {
  const { isAuthenticated, hydrating } = useAuthStore()
  if (isTWA()) return <Navigate to="/twa" replace />
  if (hydrating) return <LoadingSpinner />
  if (isAuthenticated) return <Navigate to="/dashboard" replace />
  return <Navigate to="/home" replace />
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
      <GlobalErrorBoundary>
        {/* ARCH-137 B6: зона показа резолвится ДО первого рендера страниц —
            см. contexts/DisplayTzProvider.tsx. Гейт короткий (таймаут 4с), на
            ошибке/старом бэке деградирует в Asia/Tashkent. Внутри
            GlobalErrorBoundary, чтобы исключение в самом провайдере попадало
            в штатный fallback, а не в белый экран. */}
        <DisplayTzProvider fallback={<LoadingSpinner />}>
        <BrowserRouter basename={import.meta.env.BASE_URL}>
          <RootToaster />
          <Suspense fallback={<LoadingSpinner />}>
            <Routes>
              <Route path="/login" element={<LoginPage />} />

              <Route path="/dashboard" element={<ProtectedRoute action="dashboard.use"><DashboardLayout /></ProtectedRoute>}>
                <Route index element={<PageErrorBoundary><KanbanPage /></PageErrorBoundary>} />
                <Route path="analytics" element={<ActionRoute action="requests.stats"><PageErrorBoundary><AnalyticsPage /></PageErrorBoundary></ActionRoute>} />
                <Route path="shifts" element={<ActionRoute action="shifts.manage"><PageErrorBoundary><ShiftsPage /></PageErrorBoundary></ActionRoute>} />
                <Route path="employees" element={<ActionRoute action="staff.manage"><PageErrorBoundary><EmployeesPage /></PageErrorBoundary></ActionRoute>} />
                <Route path="employees/:id" element={<ActionRoute action="staff.manage"><PageErrorBoundary><EmployeeDetailPage /></PageErrorBoundary></ActionRoute>} />
                <Route path="templates" element={<ActionRoute action="shifts.manage"><PageErrorBoundary><TemplatesPage /></PageErrorBoundary></ActionRoute>} />
                <Route path="payment-control" element={<ActionRoute action="payments.manage"><PageErrorBoundary><PaymentControlPage /></PageErrorBoundary></ActionRoute>} />
                <Route path="addresses" element={<ActionRoute action="addresses.manage"><PageErrorBoundary><AddressesPage /></PageErrorBoundary></ActionRoute>} />
                <Route path="residents" element={<ActionRoute action="residents.manage"><PageErrorBoundary><ResidentsPage /></PageErrorBoundary></ActionRoute>} />
                <Route path="residents/:id" element={<ActionRoute action="residents.manage"><PageErrorBoundary><ResidentDetailPage /></PageErrorBoundary></ActionRoute>} />
                {/* Group Intake: реестр ТГ-групп (как residents — пункт меню
                    только manager, "только manager" enforced бэкендом). */}
                <Route path="groups" element={<ActionRoute action="group_intake.manage"><PageErrorBoundary><GroupsPage /></PageErrorBoundary></ActionRoute>} />
                <Route path="board-editor" element={<ActionRoute action="board.configure"><PageErrorBoundary><BoardEditorPage /></PageErrorBoundary></ActionRoute>} />
                {/* Менеджерская очередь модерации визуальных отчётов «до/после».
                    Гард — действие work_reports.moderate (ActionRoute), его же
                    проверяет бэкенд.
                    DARK за VITE_WORK_REPORTS_ENABLED. */}
                {WORK_REPORTS_ENABLED && (
                  <Route path="work-reports" element={<ActionRoute action="work_reports.moderate"><PageErrorBoundary><WorkReportsPage /></PageErrorBoundary></ActionRoute>} />
                )}
                <Route path="feedback" element={<ActionRoute action="feedback.manage"><PageErrorBoundary><FeedbackPage /></PageErrorBoundary></ActionRoute>} />
              </Route>

              {/* access_control §9.6: контроль доступа — отдельный route group с
                  гардом ролей модуля (manager/system_admin/security_operator).
                  Вынесен из основного /dashboard, т.к. тот пускает только
                  admin/manager, а security_operator/system_admin должны попадать
                  на панель охраны. executor/inspector/applicant — не видят. */}
              <Route path="/dashboard/access" element={<ProtectedRoute action="access.events.read"><DashboardLayout /></ProtectedRoute>}>
                <Route index element={<PageErrorBoundary><AccessControlPage /></PageErrorBoundary>} />
              </Route>

              {/* access_control §6/§13.2: экраны менеджера (история проездов +
                  база доступа). Отдельный route group — гард access.registry.manage
                  (manager/system_admin), оператор охраны сюда не допускается. */}
              <Route path="/dashboard/access/history" element={<ProtectedRoute action="access.registry.manage"><DashboardLayout /></ProtectedRoute>}>
                <Route index element={<PageErrorBoundary><AccessHistoryPage /></PageErrorBoundary>} />
              </Route>
              <Route path="/dashboard/access/database" element={<ProtectedRoute action="access.registry.manage"><DashboardLayout /></ProtectedRoute>}>
                <Route index element={<PageErrorBoundary><AccessDatabasePage /></PageErrorBoundary>} />
              </Route>
              {/* access_control: «Оборудование» (зоны/въезды/камеры/шлагбаумы/
                  контроллеры). Гард — access.registry.manage; камеры/шлагбаумы/
                  контроллеры внутри доступны только system_admin (гейтинг табов). */}
              <Route path="/dashboard/access/equipment" element={<ProtectedRoute action="access.registry.manage"><DashboardLayout /></ProtectedRoute>}>
                <Route index element={<PageErrorBoundary><AccessEquipmentPage /></PageErrorBoundary>} />
              </Route>

              {/* Роли и права: смотрит тот, у кого rbac.view (по умолчанию
                  менеджер), меняет только суперадмин из ADMIN_USER_IDS. Отдельный
                  group: суперадмину не обязательно иметь dashboard.use. */}
              <Route path="/dashboard/roles" element={<ProtectedRoute action="rbac.view"><DashboardLayout /></ProtectedRoute>}>
                <Route index element={<PageErrorBoundary><RolesPage /></PageErrorBoundary>} />
              </Route>

              {/* Складской учёт материалов: номенклатура, остатки, журнал
                  операций, «на закуп». Гард — materials.manage. */}
              <Route path="/dashboard/materials" element={<ProtectedRoute action="materials.manage"><DashboardLayout /></ProtectedRoute>}>
                <Route index element={<PageErrorBoundary><MaterialsPage /></PageErrorBoundary>} />
              </Route>

              {/* Лифты: реестр/карточка/форма/календарь — отдельный route group,
                  т.к. общий /dashboard пускает только admin/manager, а реестр
                  читает и executor (elevators.read). Конфиг — только
                  manager, поэтому отдельным group'ом ниже (статический сегмент
                  `config` ранжируется выше `:id`). DARK за VITE_ELEVATORS_ENABLED. */}
              {ELEVATORS_ENABLED && (
                <Route path="/dashboard/elevators" element={<ProtectedRoute action="elevators.read"><DashboardLayout /></ProtectedRoute>}>
                  <Route index element={<PageErrorBoundary><ElevatorsPage /></PageErrorBoundary>} />
                  <Route path="new" element={<PageErrorBoundary><ElevatorFormPage /></PageErrorBoundary>} />
                  <Route path="calendar" element={<PageErrorBoundary><ElevatorsCalendarPage /></PageErrorBoundary>} />
                  <Route path=":id" element={<PageErrorBoundary><ElevatorDetailPage /></PageErrorBoundary>} />
                  <Route path=":id/edit" element={<PageErrorBoundary><ElevatorFormPage /></PageErrorBoundary>} />
                </Route>
              )}
              {ELEVATORS_ENABLED && (
                <Route path="/dashboard/elevators/config" element={<ProtectedRoute action="elevators.manage"><DashboardLayout /></ProtectedRoute>}>
                  <Route index element={<PageErrorBoundary><ElevatorsConfigPage /></PageErrorBoundary>} />
                </Route>
              )}
              {NEWS_WATCH_ENABLED && (
                <Route path="/dashboard/news-watch" element={<ProtectedRoute action="board.configure"><DashboardLayout /></ProtectedRoute>}>
                  <Route index element={<PageErrorBoundary><NewsWatchPage /></PageErrorBoundary>} />
                </Route>
              )}

              {/* Учёт ресурсов УК — нативный портируемый модуль (не iframe).
                  Splat-роут: внутренний <ResourceAccountingRoutes/> резолвит
                  подпути относительно basePath. Гард — resources.launch.
                  DARK за VITE_RESOURCES_ENABLED (edge resource-api пока 404). */}
              {RESOURCES_ENABLED && (
                <Route path="/dashboard/resource-accounting" element={<ProtectedRoute action="resources.launch"><DashboardLayout /></ProtectedRoute>}>
                  {/* index — точный путь (куда ведёт пункт меню): splat `*` не
                      матчит пустой остаток, поэтому нужен отдельный index-роут.
                      `*` — все под-пути (worksheet/meters/...) для вложенных
                      <ResourceAccountingRoutes>. Оба рендерят одну секцию. */}
                  <Route index element={<PageErrorBoundary><ResourceAccountingSection /></PageErrorBoundary>} />
                  <Route path="*" element={<PageErrorBoundary><ResourceAccountingSection /></PageErrorBoundary>} />
                </Route>
              )}

              {/* Страница жителей «Ваш дом сегодня» — публичная главная (сюда ведёт «/»). */}
              <Route path="/home" element={<PageErrorBoundary><ResidentHomePage /></PageErrorBoundary>} />

              {/* Resident board — табло для экрана в холле (публичное, standalone) */}
              <Route path="/resident-board" element={<PageErrorBoundary><ResidentBoardPage /></PageErrorBoundary>} />

              {/* Публичный архив визуальных отчётов «до/после» — полная лента
                  (в отличие от WorkReportsModule на табло, который показывает
                  только первые 6). Публичный top-level роут, вне ProtectedRoute
                  — та же форма, что и /resident-board выше. DARK за
                  VITE_WORK_REPORTS_ENABLED. */}
              {WORK_REPORTS_ENABLED && (
                <Route path="/work-reports" element={<PageErrorBoundary><WorkReportsArchivePage /></PageErrorBoundary>} />
              )}
              {/* Страница одного отчёта — цель нажатия по миниатюре в блоке на
                  табло. Отдельный URL (а не модалка): ссылку на конкретную
                  работу можно дать проверяющему органу. Объявлен ПОСЛЕ
                  статического /work-reports — react-router 6 выбирает по
                  специфичности, но порядок держим читаемым. */}
              {WORK_REPORTS_ENABLED && (
                <Route path="/work-reports/:reportId" element={<PageErrorBoundary><WorkReportDetailPage /></PageErrorBoundary>} />
              )}

              {/* Публичная страница «Лифты» (T17, Р17): полный список к сводке
                  «N из M работают» на табло; фильтры в ?status=&q=&yard=.
                  Публичный top-level роут, вне ProtectedRoute — как
                  /resident-board. Роут объявлен всегда: при выключенном
                  VITE_ELEVATORS_ENABLED страница сама редиректит на
                  /resident-board (isElevatorsEnabled()). */}
              <Route path="/elevators" element={<PageErrorBoundary><ResidentElevatorsPage /></PageErrorBoundary>} />

              {/* Applicant registration - public Telegram Mini App page */}
              <Route path="/register" element={<PageErrorBoundary><RegisterPage /></PageErrorBoundary>} />

              {/* TWA — self-contained Mini App */}
              <Route path="/twa/*" element={<PageErrorBoundary><TWAApp /></PageErrorBoundary>} />

              <Route path="/" element={<RootRedirect />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </Suspense>
        </BrowserRouter>
        </DisplayTzProvider>
      </GlobalErrorBoundary>
    </QueryClientProvider>
  )
}
