/**
 * SEC-017: TWA refresh token store — in memory only (module variable), never in
 * localStorage. A 30-day refresh token in localStorage on the shared infrasafe.uz
 * origin is exactly the XSS-exfiltratable credential SEC-017 set out to remove.
 *
 * On a page reload the module memory is cleared; the app re-authenticates from
 * fresh Telegram initData (useTWAAuth → POST /auth/twa), which Telegram
 * regenerates on every WebApp open. The access token lives in React state +
 * the twaClient Authorization header; only the refresh token is held here so the
 * 401 interceptor can mint a new access token within the same session without
 * re-running initData.
 */

// One-time purge of the pre-SEC-017 token persisted by older builds.
try {
  localStorage.removeItem('twa_refresh_token')
} catch {
  /* storage unavailable (private mode / disabled) — nothing to purge */
}

let refreshToken: string | null = null

export function getTwaRefreshToken(): string | null {
  return refreshToken
}

export function setTwaRefreshToken(token: string | null): void {
  refreshToken = token || null
}

export function clearTwaRefreshToken(): void {
  refreshToken = null
}
