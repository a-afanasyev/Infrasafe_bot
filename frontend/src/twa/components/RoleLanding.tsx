import { useQuery } from '@tanstack/react-query'
import { Navigate } from 'react-router-dom'
import { twaClient } from '../twaClient'

interface ProfileResponse {
  active_role?: string | null
}

/**
 * TWA entry point. Telegram opens the mini-app at the SPA root, which lands
 * here. We route the user into the section matching their active role so an
 * executor isn't dropped into the applicant UI — which has no path back to
 * /twa/exec (the executor section is only reachable via ExecutorTabs, and
 * those only render on /twa/exec/* routes). A role switch lives in the
 * profile pages for users who hold both roles.
 */
export default function RoleLanding() {
  const { data, isLoading, isError } = useQuery<ProfileResponse>({
    queryKey: ['profile'],
    queryFn: () => twaClient.get('/api/v2/profile').then((r) => r.data),
    staleTime: 60_000,
  })

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen text-gray-400 text-[14px]">
        Loading...
      </div>
    )
  }

  // Applicant home is the safe default (also on profile-load error).
  const target = !isError && data?.active_role === 'executor' ? '/twa/exec' : '/twa/app'
  return <Navigate to={target} replace />
}
