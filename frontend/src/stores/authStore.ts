import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { apiClient } from '../api/client'

// One-time migration purge: builds before the cookie-auth switch (§6.5)
// stored access_token / refresh_token in localStorage. The current code never
// reads them, but a stale 30-day refresh_token left in localStorage on the
// shared infrasafe.uz origin is exactly the XSS-exposed credential §6.5/R-8
// set out to eliminate. Drop them on load.
localStorage.removeItem('access_token')
localStorage.removeItem('refresh_token')

// Web SPA auth: tokens live only in httpOnly cookies (uk_access on Path=/uk/,
// uk_refresh on Path=/uk/api/). The store holds user identity for UI gating.
// TWA flow uses its own store/client (Bearer-based) — do not mix the two.
interface AuthState {
  user: { id: number; roles: string[]; first_name?: string } | null
  isAuthenticated: boolean
  login: (access_token?: string) => Promise<void>
  logout: () => Promise<void>
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      isAuthenticated: false,
      login: async () => {
        // Cookies are already set by POST /api/v2/auth/login response;
        // fetch profile to materialise UI-facing identity.
        const { data } = await apiClient.get('/api/v2/profile')
        set({ user: data, isAuthenticated: true })
      },
      logout: async () => {
        // Server clears uk_access / uk_refresh cookies; no body needed.
        await apiClient.post('/api/v2/auth/logout').catch(() => {})
        set({ user: null, isAuthenticated: false })
      },
    }),
    {
      name: 'auth-store',
      partialize: (state) => ({
        user: state.user
          ? { id: state.user.id, first_name: state.user.first_name, roles: state.user.roles }
          : null,
        isAuthenticated: state.isAuthenticated,
      }),
    }
  )
)
