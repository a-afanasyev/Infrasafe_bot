import axios from 'axios'

// Minimal axios instance for unauthenticated public endpoints (e.g. the
// resident landing board). Unlike apiClient, it has NO 401 interceptor —
// so a request without a session never triggers a redirect to /uk/login.
const BASE_URL =
  import.meta.env.VITE_API_URL ??
  import.meta.env.BASE_URL.replace(/\/$/, '')

export const publicClient = axios.create({
  baseURL: BASE_URL,
  withCredentials: false,
})
