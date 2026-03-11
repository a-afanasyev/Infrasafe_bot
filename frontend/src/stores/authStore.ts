import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { apiClient } from '../api/client'

interface AuthState {
  user: { id: number; roles: string[]; first_name?: string } | null
  isAuthenticated: boolean
  login: (access_token: string, refresh_token: string) => Promise<void>
  logout: () => Promise<void>
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      isAuthenticated: false,
      login: async (access_token, refresh_token) => {
        localStorage.setItem('access_token', access_token)
        localStorage.setItem('refresh_token', refresh_token)
        const { data } = await apiClient.get('/api/v2/profile')
        set({ user: data, isAuthenticated: true })
      },
      logout: async () => {
        const refresh_token = localStorage.getItem('refresh_token')
        if (refresh_token) {
          await apiClient.post('/api/v2/auth/logout', { refresh_token }).catch(() => {})
        }
        localStorage.clear()
        set({ user: null, isAuthenticated: false })
      },
    }),
    { name: 'auth-store' }
  )
)
