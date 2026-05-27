import { useQuery } from '@tanstack/react-query'
import { Navigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { twaClient } from '../twaClient'

interface ProfileResponse {
  roles?: string[] | null
  active_role?: string | null
}

interface Props {
  required: 'applicant' | 'executor' | 'manager'
  /** Where to send users that don't have the role. Default: /twa/app */
  fallback?: string
  children: React.ReactNode
}

/**
 * TWA-12: client-side role check for route segments that only make sense
 * for one role. An applicant who navigates (or is deep-linked) to a
 * /twa/exec/* URL would otherwise see executor pages render and silently
 * 403 on the data calls. We redirect them to the applicant landing instead.
 *
 * The server is still the source of truth — this is UX, not security.
 */
export default function RoleGuard({ required, fallback = '/twa/app', children }: Props) {
  const { t } = useTranslation()
  const { data, isLoading, isError } = useQuery<ProfileResponse>({
    queryKey: ['profile'],
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

  if (isError) {
    // Profile lookup failed — fall through and let the wrapped page hit its
    // own 401/refresh path instead of trapping the user in a guard error.
    return <>{children}</>
  }

  const roles = data?.roles ?? (data?.active_role ? [data.active_role] : [])
  if (!roles.includes(required)) {
    return <Navigate to={fallback} replace />
  }

  return <>{children}</>
}
