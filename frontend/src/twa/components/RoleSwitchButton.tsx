import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Repeat } from 'lucide-react'
import { twaClient } from '../twaClient'
import { useTelegramSDK } from '../hooks/useTelegramSDK'
import { notifyError } from '../utils/errors'

interface ProfileResponse {
  roles?: string[] | null
}

type SwitchRole = 'applicant' | 'executor' | 'inspector'

const ROLE_ROUTE: Record<SwitchRole, string> = {
  applicant: '/twa/app',
  executor: '/twa/exec',
  inspector: '/twa/inspector',
}

const ROLE_SWITCH_LABEL: Record<SwitchRole, string> = {
  applicant: 'twa.roleSwitch.toApplicant',
  executor: 'twa.roleSwitch.toExecutor',
  inspector: 'twa.roleSwitch.toInspector',
}

interface Props {
  /** Role/section to switch INTO. Renders only if the user holds this role. */
  to: SwitchRole
}

/**
 * Switch between applicant and executor modes. Only shown to users who hold
 * the target role (e.g. an executor who also lives in the complex). Flips
 * active_role server-side via PATCH /api/v2/profile/role, then routes to the
 * matching section. RoleLanding will honour the new active_role next open.
 */
export default function RoleSwitchButton({ to }: Props) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { haptic } = useTelegramSDK()

  const { data } = useQuery<ProfileResponse>({
    queryKey: ['profile'],
    queryFn: () => twaClient.get('/api/v2/profile').then((r) => r.data),
    staleTime: 60_000,
  })

  const mutation = useMutation({
    mutationFn: () => twaClient.patch('/api/v2/profile/role', { active_role: to }),
    onSuccess: () => {
      haptic('notification')
      queryClient.invalidateQueries({ queryKey: ['profile'] })
      navigate(ROLE_ROUTE[to], { replace: true })
    },
    onError: (err: unknown) => notifyError(err),
  })

  const roles = data?.roles ?? []
  if (!roles.includes(to)) return null

  return (
    <button
      onClick={() => mutation.mutate()}
      disabled={mutation.isPending}
      className="w-full flex items-center justify-center gap-2 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-2xl py-3 text-[13px] font-semibold text-emerald-600 disabled:opacity-50 mb-3"
    >
      <Repeat size={16} />
      {t(ROLE_SWITCH_LABEL[to])}
    </button>
  )
}
