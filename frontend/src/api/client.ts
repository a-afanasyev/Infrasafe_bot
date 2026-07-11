import axios from 'axios'

// All UK API requests are relative to the SPA base path (e.g. /uk/api/...).
// VITE_API_URL still wins for tests / dev with a non-default backend.
const BASE_URL =
  import.meta.env.VITE_API_URL ??
  import.meta.env.BASE_URL.replace(/\/$/, '')

// Login route lives at <base>login (e.g. /uk/login).
const LOGIN_URL = `${import.meta.env.BASE_URL}login`

export const apiClient = axios.create({
  baseURL: BASE_URL,
  withCredentials: true, // sends uk_access / uk_refresh cookies on Path=/uk/
})

// FE-047: клиент БЕЗ 401-interceptor — для auth-эндпоинтов страницы логина.
// apiClient на 401 пытается refresh → при неудаче редиректит на /login,
// что на самой странице логина перезагружало её и стирало inline-ошибку
// («неверный пароль» выглядел как молчаливый сброс формы).
export const publicClient = axios.create({
  baseURL: BASE_URL,
  withCredentials: true, // login/verify-otp ставят auth-cookies в ответе
})

let refreshPromise: Promise<void> | null = null

// F-02: cross-tab refresh coordination. The in-tab `refreshPromise` dedups
// concurrent 401s within one document, but each tab has its own module state —
// two tabs would both POST /refresh, and after the server rotates atomically the
// loser gets 401. With the family reuse-detection of a later change that loser
// would revoke the whole session. So we serialize refresh across tabs with the
// Web Locks API AND, under the lock, re-check a shared freshness marker: a tab
// that acquires the lock after another tab already refreshed skips its own POST
// (the httpOnly cookie is already rotated for every tab on this origin).
const REFRESH_MARKER_KEY = 'uk_refreshed_at'
const REFRESH_LOCK_NAME = 'uk-refresh'
const REFRESH_LOCK_KEY = 'uk_refresh_lock'
const REFRESH_LOCK_TTL_MS = 20000

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

function readRefreshMarker(): number {
  try {
    return Number(localStorage.getItem(REFRESH_MARKER_KEY)) || 0
  } catch {
    return 0
  }
}

function writeRefreshMarker(ts: number): void {
  try {
    localStorage.setItem(REFRESH_MARKER_KEY, String(ts))
  } catch {
    /* private mode / storage disabled — degrade to per-lock refresh */
  }
}

// Bounded so a hung refresh can't pin the cross-tab Web Lock indefinitely — on
// timeout the lock is released, the promise rejects, and refreshSession() falls
// through to the login redirect.
const REFRESH_TIMEOUT_MS = 15000

async function doNetworkRefresh(): Promise<void> {
  await axios.post(`${BASE_URL}/api/v2/auth/refresh`, undefined, {
    withCredentials: true,
    timeout: REFRESH_TIMEOUT_MS,
  })
  writeRefreshMarker(Date.now())
}

// Best-effort cross-tab mutex for browsers without the Web Locks API. localStorage
// has no atomic compare-and-set, so this is not a hard guarantee — but it holds the
// slot for the whole refresh round-trip, so a sibling tab waits and then sees the
// fresh `uk_refreshed_at` marker and skips. The server's atomic rotation remains the
// backstop for the residual simultaneous-write window. Web Locks (universal in the
// browsers this app targets) provides the hard guarantee; this only covers stragglers.
async function withLocalStorageLock(fn: () => Promise<void>): Promise<void> {
  const owner = `${Date.now()}-${Math.random().toString(36).slice(2)}`
  const deadline = Date.now() + REFRESH_LOCK_TTL_MS
  const owns = (): boolean => {
    try {
      return localStorage.getItem(REFRESH_LOCK_KEY)?.startsWith(`${owner}|`) ?? false
    } catch {
      return false
    }
  }
  while (Date.now() < deadline) {
    let raw: string | null = null
    try {
      raw = localStorage.getItem(REFRESH_LOCK_KEY)
    } catch {
      break // storage unavailable — give up on the lock, fall through to fn()
    }
    const expiry = raw ? Number(raw.split('|')[1]) : 0
    if (!raw || expiry < Date.now()) {
      try {
        localStorage.setItem(REFRESH_LOCK_KEY, `${owner}|${Date.now() + REFRESH_LOCK_TTL_MS}`)
      } catch {
        break
      }
      await sleep(15) // settle, then confirm we hold it (last-writer-wins arbitration)
      if (owns()) {
        try {
          await fn()
        } finally {
          try {
            if (owns()) localStorage.removeItem(REFRESH_LOCK_KEY)
          } catch {
            /* ignore */
          }
        }
        return
      }
    }
    await sleep(25)
  }
  // Couldn't acquire within the TTL — run anyway; the marker re-check inside fn
  // and the server's atomic rotation still prevent a duplicate session.
  await fn()
}

async function coordinatedRefresh(): Promise<void> {
  const startedAt = Date.now()
  const runUnderLock = async (): Promise<void> => {
    // Another tab may have refreshed while we waited for the lock — skip the
    // redundant network round-trip; the cookie is already fresh for this origin.
    if (readRefreshMarker() > startedAt) return
    await doNetworkRefresh()
  }
  const locks = (navigator as Navigator & { locks?: LockManager }).locks
  if (locks?.request) {
    await locks.request(REFRESH_LOCK_NAME, runUnderLock)
  } else {
    // No Web Locks: best-effort localStorage mutex (see withLocalStorageLock).
    await withLocalStorageLock(runUnderLock)
  }
}

/**
 * Cookie-based session refresh, deduplicated across concurrent 401s within a tab
 * (refreshPromise) AND across tabs (Web Locks + shared freshness marker). Shared
 * by every API client (main apiClient + domain accessClient). The server reads
 * the uk_refresh httpOnly cookie and sets a fresh uk_access cookie in the
 * response — no body, no token plumbing in JS. On failure the user is sent to
 * the login page and the rejection propagates.
 */
export function refreshSession(): Promise<void> {
  if (!refreshPromise) {
    refreshPromise = coordinatedRefresh()
      .catch((err) => {
        window.location.href = LOGIN_URL
        throw err
      })
      .finally(() => { refreshPromise = null })
  }
  return refreshPromise
}

apiClient.interceptors.response.use(
  (r) => r,
  async (error) => {
    const originalRequest = error.config as (typeof error.config) & { _retry?: boolean }
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true
      try {
        await refreshSession()
        return apiClient(originalRequest)
      } catch (refreshError) {
        return Promise.reject(refreshError)
      }
    }
    return Promise.reject(error)
  }
)
