import axios from 'axios'

// Minimal axios instance for unauthenticated public endpoints (e.g. the
// resident landing board). Unlike apiClient, it has NO 401 interceptor —
// so a request without a session never triggers a redirect to /uk/login.
// Exported so callers that need a raw URL (e.g. an <img src> straight to a
// public media-streaming endpoint, never fetched via axios/JSON — see
// usePublicWorkReports.ts) can reuse this computation instead of
// duplicating it.
//
// NAMING TRAP: `api/client.ts` ALSO exports something called `publicClient`
// — a DIFFERENT, unrelated axios instance (withCredentials: true, for
// login/OTP flows). Same name, different module, opposite credentials
// setting. Importing the wrong one type-checks fine and "works" in the
// common case — it just silently attaches session cookies to a request
// meant to be anonymous. For anonymous/public board & feed endpoints, THIS
// file's `publicClient` (withCredentials: false) is the one you want.
export const BASE_URL =
  import.meta.env.VITE_API_URL ??
  import.meta.env.BASE_URL.replace(/\/$/, '')

export const publicClient = axios.create({
  baseURL: BASE_URL,
  withCredentials: false,
})
