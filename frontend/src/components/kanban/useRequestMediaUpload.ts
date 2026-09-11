import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { apiClient } from '../../api/client'
import { safeErrorMessage } from '@/utils/errorMessage'

/**
 * Загрузка медиа в заявку из карточки дашборда (менеджер).
 *
 * Два вида: `request` — фото проблемы (заявка оформлена по телефону, житель
 * прислал фото в мессенджер), `completion` — фотоотчёт исполнителя. Категории
 * зеркалят FileCategories media-прокси (SEC-021 whitelist); видео — по MIME.
 *
 * Последовательно и best-effort (как TWA CompletionReport): падение одного
 * файла не отменяет остальные; частичный успех тоже инвалидирует список.
 */
export type RequestMediaKind = 'request' | 'completion'

// Accept зеркалит magic-byte allowlist прокси (jpeg/png/gif/mp4/mov) — файл иного
// типа всё равно упрётся в 415 на сервере, так что не даём его выбрать.
export const UPLOAD_ACCEPT = 'image/jpeg,image/png,image/gif,video/mp4,video/quicktime'

const CATEGORY: Record<RequestMediaKind, { photo: string; video: string }> = {
  request: { photo: 'request_photo', video: 'request_video' },
  completion: { photo: 'completion_photo', video: 'completion_video' },
}

const TOAST_KEYS: Record<RequestMediaKind, { ok: string; fail: string }> = {
  request: { ok: 'toast.requestPhotosUploaded', fail: 'toast.requestPhotosUploadFailed' },
  completion: { ok: 'toast.workPhotosUploaded', fail: 'toast.workPhotosUploadFailed' },
}

export function uploadErrorHint(error: unknown, t: (k: string) => string): string {
  const status = (error as { response?: { status?: number } })?.response?.status
  // 413 может прийти от edge-nginx раньше нашего лимита — тела с detail там нет.
  if (status === 413) return t('kanban.fileTooLarge')
  if (status === 415) return t('kanban.unsupportedFileType')
  return safeErrorMessage(error, 'An error occurred')
}

export function categoryFor(kind: RequestMediaKind, file: File): string {
  return file.type.startsWith('video/') ? CATEGORY[kind].video : CATEGORY[kind].photo
}

export function useRequestMediaUpload({ requestNumber, kind }: { requestNumber: string; kind: RequestMediaKind }) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (files: File[]) => {
      const failures: unknown[] = []
      for (const file of files) {
        const form = new FormData()
        form.append('file', file)
        form.append('request_number', requestNumber)
        form.append('category', categoryFor(kind, file))
        try {
          await apiClient.post('/api/v2/media/upload', form, {
            headers: { 'Content-Type': 'multipart/form-data' },
          })
        } catch (error) {
          failures.push(error)
        }
      }
      return { total: files.length, failures }
    },
    onSuccess: ({ total, failures }) => {
      if (failures.length < total) {
        queryClient.invalidateQueries({ queryKey: ['request-media', requestNumber] })
      }
      if (failures.length === 0) {
        toast.success(t(TOAST_KEYS[kind].ok))
      } else {
        toast.error(t(TOAST_KEYS[kind].fail), {
          description: uploadErrorHint(failures[failures.length - 1], t),
        })
      }
    },
  })
}
