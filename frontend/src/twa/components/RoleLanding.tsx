import { useQuery } from '@tanstack/react-query'
import { Navigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { twaClient } from '../twaClient'

interface ProfileResponse {
  roles?: string[] | null
  active_role?: string | null
}

/** Roles that own a TWA section, mapped to their landing route. */
const ROLE_ROUTE: Record<string, string> = {
  applicant: '/twa/app',
  executor: '/twa/exec',
  inspector: '/twa/inspector',
}

/**
 * Manager has no own TWA section. If a manager also holds a TWA-capable role
 * we land them there (priority order); a manager-only account gets a static
 * "TWA unavailable" screen rather than a redirect — redirecting would bounce
 * /twa → /twa/app → RoleGuard → /twa and loop forever.
 */
const MANAGER_FALLBACK_PRIORITY = ['inspector', 'applicant', 'executor'] as const

/**
 * TWA entry point. Telegram opens the mini-app at the SPA root, which lands
 * here. We route the user into the section matching their active role so an
 * executor isn't dropped into the applicant UI. ALL active roles are mapped
 * explicitly; manager falls back by membership priority. A role switch lives
 * in the section headers for users who hold more than one role.
 */
export default function RoleLanding() {
  const { t } = useTranslation()
  const { data, isLoading, isError } = useQuery<ProfileResponse>({
    queryKey: ['twa', 'profile'],
    queryFn: () => twaClient.get('/api/v2/profile').then((r) => r.data),
    staleTime: 60_000,
  })

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen text-gray-400 text-[14px]">
        {t('common.loading')}
      </div>
    )
  }

  // On profile-load error, applicant home is the safe default.
  if (isError) {
    return <Navigate to="/twa/app" replace />
  }

  const roles = data?.roles ?? (data?.active_role ? [data.active_role] : [])
  const activeRole = data?.active_role ?? ''

  // 1) Active role owns a section → go straight there.
  if (ROLE_ROUTE[activeRole]) {
    return <Navigate to={ROLE_ROUTE[activeRole]} replace />
  }

  // 2) Manager (or any section-less active role): fall back to a held
  //    TWA-capable role by priority.
  const fallbackRole = MANAGER_FALLBACK_PRIORITY.find((r) => roles.includes(r))
  if (fallbackRole) {
    return <Navigate to={ROLE_ROUTE[fallbackRole]} replace />
  }

  // 3) Manager-only (no TWA section): static screen, NO redirect (avoids loop).
  return (
    <div className="flex items-center justify-center min-h-screen px-6 text-center text-gray-500 dark:text-gray-400 text-[14px]">
      {t('twa.roleLanding.unavailable')}
    </div>
  )
}
