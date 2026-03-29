/**
 * TWA-specific axios client.
 * Separate from dashboard's apiClient to avoid auth header conflicts.
 * Token is set via TWAContent useEffect, not via localStorage interceptor.
 */
import axios from 'axios'

const BASE_URL = import.meta.env.VITE_API_URL ?? ''

export const twaClient = axios.create({ baseURL: BASE_URL })
