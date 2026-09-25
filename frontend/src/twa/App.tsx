import { Routes, Route, Navigate, useLocation } from 'react-router'
import { QueryClientProvider } from '@tanstack/react-query'
import { useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import MeterEntryScreen from './pages/meter-entry/MeterEntryScreen'
import { useTWAAuth } from './hooks/useTWAAuth'
import { useProfileLanguage } from './hooks/useProfileLanguage'
import { useTelegramSDK } from './hooks/useTelegramSDK'
import { ApplicantTabs } from './components/BottomTabBar'
import { ExecutorTabs } from './components/ExecutorTabs'
import { twaClient } from './twaClient'
import { createTwaQueryClient } from './queryRetry'
import OfflineIndicator from '../components/shared/OfflineIndicator'
import RoleGuard from './components/RoleGuard'
import RoleLanding from './components/RoleLanding'
import { Toaster } from '../components/ui/sonner'
import '../i18n'

// Shared pages
import FeedbackPage from './pages/FeedbackPage'

// Applicant pages
import HomePage from './pages/applicant/HomePage'
import RequestsPage from './pages/applicant/RequestsPage'
import CreatePage from './pages/applicant/CreatePage'
import AcceptancePage from './pages/applicant/AcceptancePage'
import ProfilePage from './pages/applicant/ProfilePage'
import RequestDetailPage from './pages/applicant/RequestDetailPage'
import AccessPage from './pages/access/AccessPage'
import VehicleRequestPage from './pages/access/VehicleRequestPage'
import PassNewPage from './pages/access/PassNewPage'

// Inspector pages
import InspectorCreatePage from './pages/inspector/CreatePage'

// Executor pages
import TasksPage from './pages/executor/TasksPage'
import ShiftPage from './pages/executor/ShiftPage'
import PurchasePage from './pages/executor/PurchasePage'
import ArchivePage from './pages/executor/ArchivePage'
import ExecutorProfilePage from './pages/executor/ProfilePage'
import MyShiftsPage from './pages/executor/MyShiftsPage'
import CompletionReport from './pages/executor/CompletionReport'

// Простой режим исполнителя (/twa/s/*)
import { ExecHomeGate, ExecTaskEntry } from './simple/ExecGates'
import SimpleShell from './simple/SimpleShell'
import SimpleLangPage from './simple/pages/LangPage'
import SimpleMinePage from './simple/pages/MinePage'
import SimplePoolPage from './simple/pages/PoolPage'
import SimpleTaskPage from './simple/pages/TaskPage'
import SimpleDonePage from './simple/pages/DonePage'
import SimpleProblemPage from './simple/pages/ProblemPage'
import SimpleShiftPage from './simple/pages/ShiftPage'

// У простого режима своя полоса «нет связи» (со счётчиком неотправленных фото).
const SIMPLE_PATH = /^\/twa\/s(\/|$)/

const queryClient = createTwaQueryClient()

/** Язык профиля перекрывает Telegram language_code (монтируется только после авторизации). */
function ProfileLanguageSync() {
  useProfileLanguage()
  return null
}

function TWAContent() {
  const { t } = useTranslation()
  const { accessToken, isLoading, isAuthenticated } = useTWAAuth()
  const location = useLocation()

  // Set auth header for TWA-specific client (not shared apiClient)
  useEffect(() => {
    if (accessToken) {
      twaClient.defaults.headers.common['Authorization'] = `Bearer ${accessToken}`
    }
  }, [accessToken])

  // Экран контролёра «Ввод показаний» авторизуется НАПРЯМУЮ в ресурс-сервис по
  // initData (UK-JWT не требуется) — рендерим ДО общего UK-auth-гейта, чтобы
  // контролёр без UK-role-landing не упирался в 🔒.
  if (location.pathname.endsWith('/meter-entry')) {
    return <MeterEntryScreen />
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-gray-50 dark:bg-gray-950">
        <p className="text-gray-400 text-[14px]">{t('common.loading')}</p>
      </div>
    )
  }

  if (!isAuthenticated) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen bg-gray-50 dark:bg-gray-950 p-6 text-center">
        <p className="text-[40px] mb-3">🔒</p>
        <p className="text-gray-500 text-[14px]">{t('twa.openViaBot')}</p>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-950 text-gray-900 dark:text-gray-100">
      <ProfileLanguageSync />
      {!SIMPLE_PATH.test(location.pathname) && <OfflineIndicator />}
      <Toaster position="top-center" richColors closeButton />
      <Routes>
        <Route path="/" element={<RoleLanding />} />

        {/* Applicant routes — wrapped in RoleGuard (план «Обходчик») so a
            non-applicant (e.g. inspector) deep-linking here is bounced to
            RoleLanding (fallback="/twa") instead of seeing applicant UI 403. */}
        <Route path="/app" element={<RoleGuard required="applicant" fallback="/twa"><HomePage /><ApplicantTabs /></RoleGuard>} />
        <Route path="/app/requests" element={<RoleGuard required="applicant" fallback="/twa"><RequestsPage /><ApplicantTabs /></RoleGuard>} />
        <Route path="/app/create" element={<RoleGuard required="applicant" fallback="/twa"><CreatePage /><ApplicantTabs /></RoleGuard>} />
        <Route path="/app/acceptance" element={<RoleGuard required="applicant" fallback="/twa"><AcceptancePage /><ApplicantTabs /></RoleGuard>} />
        <Route path="/app/profile" element={<RoleGuard required="applicant" fallback="/twa"><ProfilePage /><ApplicantTabs /></RoleGuard>} />
        <Route path="/app/requests/:number" element={<RoleGuard required="applicant" fallback="/twa"><RequestDetailPage /></RoleGuard>} />

        {/* Контроль доступа жителя (ANPR/шлагбаум): авто, пропуска, проезды.
            applicant-API /api/v1/access/* через twaClient (same-origin в проде). */}
        <Route path="/app/access" element={<RoleGuard required="applicant" fallback="/twa"><AccessPage /><ApplicantTabs /></RoleGuard>} />
        <Route path="/app/access/vehicle-request" element={<RoleGuard required="applicant" fallback="/twa"><VehicleRequestPage /></RoleGuard>} />
        <Route path="/app/access/pass-new" element={<RoleGuard required="applicant" fallback="/twa"><PassNewPage /></RoleGuard>} />

        {/* Inspector route — building-level заявка с обхода (двор→дом). */}
        <Route path="/inspector" element={<RoleGuard required="inspector" fallback="/twa"><InspectorCreatePage /></RoleGuard>} />

        {/* Executor routes — wrapped in RoleGuard (TWA-12) so an applicant
            opening /twa/exec/* gets sent back to /twa/app rather than seeing
            an empty executor UI with 403s in the network panel. */}
        <Route path="/exec" element={<RoleGuard required="executor"><ExecHomeGate><TasksPage /><ExecutorTabs /></ExecHomeGate></RoleGuard>} />
        <Route path="/exec/shift" element={<RoleGuard required="executor"><ShiftPage /><ExecutorTabs /></RoleGuard>} />
        <Route path="/exec/purchase" element={<RoleGuard required="executor"><PurchasePage /><ExecutorTabs /></RoleGuard>} />
        <Route path="/exec/archive" element={<RoleGuard required="executor"><ArchivePage /><ExecutorTabs /></RoleGuard>} />
        <Route path="/exec/profile" element={<RoleGuard required="executor"><ExecutorProfilePage /><ExecutorTabs /></RoleGuard>} />
        {/* Ссылка бота на заявку: simple → /twa/s/task/:n, ?action=done → «Готово»/отчёт. */}
        <Route path="/exec/tasks/:number" element={<RoleGuard required="executor"><ExecTaskEntry /></RoleGuard>} />
        <Route path="/exec/shifts" element={<RoleGuard required="executor"><MyShiftsPage /></RoleGuard>} />
        <Route path="/exec/report/:number" element={<RoleGuard required="executor"><CompletionReport /></RoleGuard>} />

        {/* Простой режим исполнителя: крупные кнопки, фото вместо текста, очередь «Готово». */}
        <Route path="/s/lang" element={<RoleGuard required="executor"><SimpleLangPage /></RoleGuard>} />
        <Route path="/s" element={<RoleGuard required="executor"><SimpleShell /></RoleGuard>}>
          <Route index element={<SimpleMinePage />} />
          <Route path="pool" element={<SimplePoolPage />} />
          <Route path="task/:number" element={<SimpleTaskPage />} />
          <Route path="task/:number/done" element={<SimpleDonePage />} />
          <Route path="task/:number/problem" element={<SimpleProblemPage />} />
          <Route path="shift" element={<SimpleShiftPage />} />
        </Route>

        {/* Обратная связь — общий маршрут для обеих ролей, без таб-бара */}
        <Route path="/feedback" element={<FeedbackPage />} />

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
