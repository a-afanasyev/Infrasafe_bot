import { apiClient } from './client'

/**
 * Профиль текущего пользователя дашборда (cookie-сессия apiClient).
 *
 * Разовые императивные вызовы модалок «Сменить email» / «Сменить пароль»: кэша
 * react-query у профиля на дашборде нет (identity живёт в authStore), поэтому
 * это функции API-слоя, а не query-хуки (A9-P3-21).
 */
export interface ProfileContact {
  email?: string | null
}

export function fetchProfileContact(): Promise<ProfileContact> {
  return apiClient.get('/api/v2/profile').then(r => r.data)
}

export function updateProfileEmail(email: string): Promise<unknown> {
  return apiClient.patch('/api/v2/profile', { email })
}

export interface SetPasswordBody {
  password: string
  confirm_password: string
  current_password?: string
}

export function submitPasswordChange(body: SetPasswordBody): Promise<unknown> {
  return apiClient.post('/api/v2/auth/set-password', body)
}
