import { useQuery } from '@tanstack/react-query'
import { twaClient } from '../../twaClient'

interface ProfileResponse {
  simple_mode?: boolean | null
}

/** Флаг простого режима из общего профиля (['twa','profile'] — кэш RoleGuard). */
export function useSimpleMode(): { isLoading: boolean; simple: boolean } {
  const { data, isLoading } = useQuery<ProfileResponse>({
    queryKey: ['twa', 'profile'],
    queryFn: () => twaClient.get('/api/v2/profile').then((r) => r.data),
    staleTime: 60_000,
  })
  return { isLoading, simple: data?.simple_mode === true }
}
