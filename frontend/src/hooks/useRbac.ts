import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { isAxiosError } from 'axios'
import i18n from '../i18n'
import { apiClient } from '../api/client'
import { safeErrorMessage } from '@/utils/errorMessage'

// Админка ролей. API живёт под /api/v2/shifts/employees — этот префикс уже
// открыт на edge обеих площадок (см. api/rbac/router.py).
const BASE = '/api/v2/shifts/employees'

export interface RbacAction {
  key: string
  title: string
  area: string
  approved_only: boolean
  superadmin_only: boolean
  default_roles: string[]
}

export interface RbacRole {
  key: string
  title: string
  description?: string | null
  is_system: boolean
  actions: string[]
  customized: string[]
  users_count: number
}

export interface RbacRolesResponse {
  roles: RbacRole[]
  can_edit: boolean
}

export interface UserRoles {
  user_id: number
  roles: string[]
  active_role?: string | null
  is_superadmin: boolean
  can_edit: boolean
}

const ROLES_KEY = ['rbac', 'roles']
const userRolesKey = (id: number) => ['rbac', 'user', id]

function errorText(error: unknown): string {
  if (isAxiosError(error) && typeof error.response?.data?.detail === 'string') {
    return error.response.data.detail
  }
  return safeErrorMessage(error, 'Error')
}

export function useRbacCatalog() {
  return useQuery<RbacAction[]>({
    queryKey: ['rbac', 'catalog'],
    queryFn: () => apiClient.get(`${BASE}/rbac/catalog`).then((r) => r.data),
    staleTime: 5 * 60_000,
  })
}

export function useRbacRoles() {
  return useQuery<RbacRolesResponse>({
    queryKey: ROLES_KEY,
    queryFn: () => apiClient.get(`${BASE}/rbac/roles`).then((r) => r.data),
    staleTime: 10_000,
  })
}

function useRolesMutation<TVars>(fn: (vars: TVars) => Promise<unknown>, okKey: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSuccess: () => {
      toast.success(i18n.t(okKey))
      queryClient.invalidateQueries({ queryKey: ['rbac'] })
    },
    onError: (error: unknown) => {
      toast.error(i18n.t('rbac.saveFailed'), { description: errorText(error) })
    },
  })
}

export function useCreateRole() {
  return useRolesMutation(
    (body: { key: string; title: string; description?: string; actions: string[] }) =>
      apiClient.post(`${BASE}/rbac/roles`, body),
    'rbac.created',
  )
}

export function useUpdateRole() {
  return useRolesMutation(
    ({ key, ...body }: { key: string; title?: string; description?: string; actions?: string[] }) =>
      apiClient.put(`${BASE}/rbac/roles/${key}`, body),
    'rbac.saved',
  )
}

export function useResetRole() {
  return useRolesMutation((key: string) => apiClient.post(`${BASE}/rbac/roles/${key}/reset`), 'rbac.resetDone')
}

export function useDeleteRole() {
  return useRolesMutation((key: string) => apiClient.delete(`${BASE}/rbac/roles/${key}`), 'rbac.deleted')
}

export function useUserRoles(userId: number | null) {
  return useQuery<UserRoles>({
    queryKey: userRolesKey(userId ?? 0),
    queryFn: () => apiClient.get(`${BASE}/${userId}/roles`).then((r) => r.data),
    enabled: userId != null,
  })
}

export function useSetUserRoles(userId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (roles: string[]) => apiClient.put(`${BASE}/${userId}/roles`, { roles }).then((r) => r.data),
    onSuccess: () => {
      toast.success(i18n.t('rbac.userRolesSaved'))
      queryClient.invalidateQueries({ queryKey: ['rbac'] })
      queryClient.invalidateQueries({ queryKey: ['employee', userId] })
    },
    onError: (error: unknown) => {
      toast.error(i18n.t('rbac.saveFailed'), { description: errorText(error) })
    },
  })
}
