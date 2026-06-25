import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'
import { apiClient, publicClient } from '../api/client'

// One-time migration purge: builds before the cookie-auth switch (§6.5)
// stored access_token / refresh_token in localStorage. The current code never
// reads them, but a stale 30-day refresh_token left in localStorage on the
// shared infrasafe.uz origin is exactly the XSS-exposed credential §6.5/R-8
// set out to eliminate. Drop them on load.
localStorage.removeItem('access_token')
localStorage.removeItem('refresh_token')
// SEC-018: prior builds persisted UI identity (id/roles) under localStorage
// 'auth-store'. We now persist to sessionStorage (below); purge the stale
// localStorage copy so an XSS can't read roles/id after this deploy.
localStorage.removeItem('auth-store')

// Web SPA auth: tokens live only in httpOnly cookies (uk_access on Path=/uk/,
// uk_refresh on Path=/uk/api/). The store holds user identity for UI gating.
// TWA flow uses its own store/client (Bearer-based) — do not mix the two.
interface AuthState {
  user: { id: number; roles: string[]; first_name?: string; has_password?: boolean } | null
  isAuthenticated: boolean
  // True until the cold-start cookie probe (bootstrap) resolves. Route guards
  // render a spinner while hydrating instead of bouncing to /login, so a fresh
  // tab with a valid (shared) httpOnly cookie isn't wrongly treated as logged out.
  hydrating: boolean
  bootstrap: () => Promise<void>
  login: (access_token?: string) => Promise<void>
  logout: () => Promise<void>
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      user: null,
      isAuthenticated: false,
      hydrating: true,
      // Cold-start session recovery. The UI auth flag lives in sessionStorage
      // (SEC-018, per-tab), but the httpOnly cookies are shared across tabs — so a
      // new tab (e.g. an InfraSafe "Открыть в УК" deep-link opened via target=_blank)
      // starts with no flag yet a live session. Probe /profile with the cookie to
      // recover it. Uses publicClient (no 401-redirect interceptor) and a manual
      // refresh fallback so a merely-expired access cookie doesn't drop the session,
      // and a genuine no-session case fails quietly → guards redirect to /login.
      bootstrap: async () => {
        if (get().isAuthenticated) {
          set({ hydrating: false })
          return
        }
        try {
          const { data } = await publicClient.get('/api/v2/profile')
          set({ user: data, isAuthenticated: true, hydrating: false })
        } catch {
          try {
            await publicClient.post('/api/v2/auth/refresh')
            const { data } = await publicClient.get('/api/v2/profile')
            set({ user: data, isAuthenticated: true, hydrating: false })
          } catch {
            set({ hydrating: false })
          }
        }
      },
      login: async () => {
        // Cookies are already set by POST /api/v2/auth/login response;
        // fetch profile to materialise UI-facing identity.
        const { data } = await apiClient.get('/api/v2/profile')
        set({ user: data, isAuthenticated: true, hydrating: false })
      },
      logout: async () => {
        // Server clears uk_access / uk_refresh cookies; no body needed.
        await apiClient.post('/api/v2/auth/logout').catch(() => {})
        set({ user: null, isAuthenticated: false })
      },
    }),
    {
      name: 'auth-store',
      // SEC-018: identity lives in sessionStorage, not localStorage — survives a
      // reload within the tab (ProtectedRoute reads isAuthenticated synchronously,
      // so the cookie-backed session stays usable) but is cleared on tab close,
      // shrinking the XSS exposure window from 30 days to the tab lifetime.
      storage: createJSONStorage(() => sessionStorage),
      partialize: (state) => ({
        user: state.user
          ? { id: state.user.id, first_name: state.user.first_name, roles: state.user.roles }
          : null,
        isAuthenticated: state.isAuthenticated,
      }),
    }
  )
)
