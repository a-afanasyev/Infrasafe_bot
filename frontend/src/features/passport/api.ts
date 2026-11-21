import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import axios from 'axios'
import { toast } from 'sonner'
import { useTranslation } from 'react-i18next'
import { apiClient } from '../../api/client'

/**
 * Паспорт дома (/api/v2/passports): типы ответа и React-Query хуки.
 * Форму описывает схема с сервера — фронт её только рисует.
 */

export const PASSPORTS_BASE = '/api/v2/passports'

export type ShowIf = [string, string[]] | null

export interface PassportOption {
  key: string
  ru: string
  uz: string
  other: boolean
}

export interface PassportField {
  kind: 'field'
  key: string
  type: 'int' | 'decimal' | 'choice' | 'text'
  ru: string
  uz: string
  unit: string | null
  form_no: string | null
  computed: boolean
  share: string | null
  show_if: ShowIf
  options?: PassportOption[]
}

export interface PassportGroup {
  kind: 'group'
  key: string
  ru: string
  uz: string
  share: string | null
  show_if: ShowIf
  fields: PassportField[]
}

export type PassportItem = PassportField | PassportGroup

export interface PassportSection {
  key: string
  no: number | null
  ru: string
  uz: string
  items: PassportItem[]
}

export interface PassportSchema {
  version: number
  sections: PassportSection[]
}

export type PassportStatus = 'not_started' | 'collecting' | 'inspected' | 'filled' | 'signed'
export type PassportRow = Record<string, string | number | null>
export type PassportValue = string | number | null | PassportRow[]
export type PassportValues = Record<string, PassportValue>

export interface PassportSummary {
  building_id: number
  address: string
  status: PassportStatus
  version: number
  revision_no: number
  progress: { done: number; total: number }
  editable: boolean
}

export interface PassportMeta {
  inspection_date: string | null
  responsible_name: string | null
  note: string | null
}

export interface PassportPhoto {
  id: number
  section: string
  uploaded_by_name: string | null
  uploaded_at: string | null
}

export interface PassportView extends PassportSummary {
  photos: PassportPhoto[]
  values: PassportValues
  unknown: Record<string, string>
  absent: string[]
  shared_from: Record<string, number>
  meta: PassportMeta
  issues: { key: string; code: string }[]
  missing: string[]
  hints: Record<string, string | number | null>
  updated_at: string | null
  updated_by_name: string | null
}

export interface PassportPatch {
  values?: PassportValues
  unknown?: Record<string, string | null>
  absent?: Record<string, boolean>
  shared_from?: Record<string, number | null>
  meta?: Partial<PassportMeta>
}

export interface PassportEvent {
  id: number
  kind: string
  changes: Record<string, unknown>
  reason: string | null
  actor_name: string | null
  created_at: string | null
}

export interface PassportRevisionHead {
  revision_no: number
  schema_version: number
  signed_by_name: string | null
  signed_at: string | null
}

export interface PassportRevision extends PassportRevisionHead {
  schema: PassportSchema
  values: PassportValues
  unknown: Record<string, string>
  absent: string[]
  shared_from: Record<string, number>
  meta: PassportMeta & { address?: string }
  photos: PassportPhoto[]
}

export const passportKeys = {
  schema: ['passport-schema'] as const,
  list: ['passports'] as const,
  detail: (id: number) => ['passport', id] as const,
  history: (id: number) => ['passport-history', id] as const,
  revisions: (id: number) => ['passport-revisions', id] as const,
}

const get = <T,>(path: string): Promise<T> => apiClient.get(`${PASSPORTS_BASE}${path}`).then((r) => r.data)

export function usePassportSchema() {
  return useQuery<PassportSchema>({ queryKey: ['passport-schema'], queryFn: () => get('/schema'), staleTime: Infinity })
}

export function usePassports() {
  return useQuery<PassportSummary[]>({ queryKey: ['passports'], queryFn: () => get('') })
}

export function usePassport(id: number) {
  return useQuery<PassportView>({ queryKey: ['passport', id], queryFn: () => get(`/buildings/${id}`) })
}

export function usePassportHistory(id: number, enabled: boolean) {
  return useQuery<PassportEvent[]>({ queryKey: ['passport-history', id], queryFn: () => get(`/buildings/${id}/history`), enabled })
}

export function usePassportRevisions(id: number, enabled: boolean) {
  return useQuery<PassportRevisionHead[]>({ queryKey: ['passport-revisions', id], queryFn: () => get(`/buildings/${id}/revisions`), enabled })
}

export function usePassportRevision(id: number, no: number | null) {
  return useQuery<PassportRevision>({
    queryKey: ['passport-revision', id, no],
    queryFn: () => get(`/buildings/${id}/revisions/${no}`),
    enabled: no !== null,
    staleTime: Infinity, // редакция неизменяема
  })
}

/** Код отказа сервиса (`detail.code`) либо null — тогда показываем общий текст. */
export function passportErrorCode(error: unknown): string | null {
  if (!axios.isAxiosError(error)) return null
  const detail = error.response?.data?.detail
  return detail && typeof detail === 'object' && typeof detail.code === 'string' ? detail.code : null
}

type Write =
  | { op: 'patch'; body: PassportPatch }
  | { op: 'status'; status: Exclude<PassportStatus, 'signed'> }
  | { op: 'sign' }
  | { op: 'reopen'; reason: string }

/**
 * Любая запись в паспорт. Версию берём из кэша в момент отправки, ответ сервера
 * кладём в кэш. На отказ паспорт перечитывается: при 409 `stale` форма покажет
 * актуальное значение пункта, а не затрёт его молча.
 */
export function usePassportWrite(id: number) {
  const qc = useQueryClient()
  const { t } = useTranslation()
  return useMutation<PassportView, unknown, Write>({
    mutationFn: (write) => {
      const expected_version = qc.getQueryData<PassportView>(passportKeys.detail(id))?.version ?? 0
      const url = `${PASSPORTS_BASE}/buildings/${id}`
      const call =
        write.op === 'patch' ? apiClient.patch(url, { ...write.body, expected_version })
        : write.op === 'status' ? apiClient.post(`${url}/status`, { status: write.status, expected_version })
        : write.op === 'sign' ? apiClient.post(`${url}/sign`, { expected_version })
        : apiClient.post(`${url}/reopen`, { reason: write.reason, expected_version })
      return call.then((r) => r.data)
    },
    onSuccess: (data, write) => {
      // Ответы двух быстрых правок могут прийти не по порядку: более старое
      // состояние не должно затирать новое.
      qc.setQueryData<PassportView>(passportKeys.detail(id), (old) => (old && old.version > data.version ? old : data))
      qc.invalidateQueries({ queryKey: passportKeys.list })
      qc.invalidateQueries({ queryKey: passportKeys.history(id) })
      if (write.op !== 'patch') qc.invalidateQueries({ queryKey: passportKeys.revisions(id) })
    },
    onError: (error, write) => {
      const keys: unknown = axios.isAxiosError(error) ? error.response?.data?.detail?.keys : null
      const raw = passportErrorCode(error)
      // Пропущенная дата осмотра не видна в списке незаполненных пунктов — называем её прямо;
      // у подписи и статуса «устарело» значит «паспорт изменился», а не «пункт».
      const code = raw === 'incomplete' && Array.isArray(keys) && keys.includes('meta.inspection_date') ? 'no_inspection_date'
        : raw === 'stale' && write.op !== 'patch' ? 'stale_status' : raw
      toast.error(t(`housePassport.errors.${code ?? 'generic'}`, { defaultValue: t('housePassport.errors.generic') }))
      qc.invalidateQueries({ queryKey: passportKeys.detail(id) })
    },
  })
}

const LEASE_MS = 130_000 // аренда загрузки на сервере — 2 минуты

/**
 * Одна загрузка фото: ключ операции один на все попытки, поэтому повтор после
 * обрыва сети, 503 или «ещё выполняется» не создаёт второго файла. «Ещё
 * выполняется» ждём до конца аренды: иначе пользователь выберет файл заново
 * (с новым ключом) и получит два фото.
 */
export async function uploadPassportPhoto(buildingId: number, section: string, file: File, pauseMs = 5000): Promise<void> {
  const opKey = crypto.randomUUID()
  const started = Date.now()
  for (let attempt = 1; ; attempt += 1) {
    const form = new FormData()
    form.append('photo', file)
    form.append('section', section)
    form.append('op_key', opKey)
    try {
      await apiClient.post(`${PASSPORTS_BASE}/buildings/${buildingId}/photos`, form)
      return
    } catch (error) {
      const code = passportErrorCode(error)
      const waiting = code === 'in_progress' && Date.now() - started < LEASE_MS
      const transient = code === 'media_unavailable' || (code === null && axios.isAxiosError(error) && !error.response)
      if (!waiting && !(transient && attempt < 3)) throw error
      await new Promise((resolve) => setTimeout(resolve, pauseMs))
    }
  }
}
