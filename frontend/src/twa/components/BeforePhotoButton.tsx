import { useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { Camera } from 'lucide-react'
import { twaClient } from '../twaClient'
import { downscaleImage } from '../utils/downscaleImage'
import { BEFORE_PHOTO_LIMIT, useBeforePhotoIds } from '../simple/api'
import { isClosed } from '../simple/model'
import { newIdempotencyKey } from '../simple/queue/policy'

// Как фото «после» простого режима: хватает, чтобы увидеть место, и уходит по плохой сети.
const DOWNSCALE = { maxDimension: 1280, thresholdBytes: 400_000 }
// Запас больше edge-бюджета (30 с), но не бесконечно — как sendQueued.
const UPLOAD_TIMEOUT_MS = 60_000

interface Props {
  requestNumber: string
  status: string
}

/**
 * «Добавить фото до» обычного TWA исполнителя: в любом незакрытом статусе, до 4
 * на заявку (с учётом уже загруженных). Каждое фото — отдельный POST
 * /before-photo со своим ключом идемпотентности. Офлайн-очереди здесь нет (как
 * у фотоотчёта обычного режима) — она есть в простом режиме.
 */
export default function BeforePhotoButton({ requestNumber, status }: Props) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const inputRef = useRef<HTMLInputElement>(null)
  const [busy, setBusy] = useState(false)
  const ids = useBeforePhotoIds(requestNumber)

  if (isClosed(status)) return null
  const left = BEFORE_PHOTO_LIMIT - ids.length

  const upload = async (picked: File[]) => {
    setBusy(true)
    let sent = 0
    let failed = 0
    for (const file of picked.slice(0, Math.max(0, left))) {
      try {
        const form = new FormData()
        form.append('photo', await downscaleImage(file, DOWNSCALE))
        form.append('idempotency_key', newIdempotencyKey())
        await twaClient.post(`/api/v2/requests/${encodeURIComponent(requestNumber)}/before-photo`, form, {
          timeout: UPLOAD_TIMEOUT_MS,
        })
        sent += 1
      } catch {
        failed += 1
      }
    }
    setBusy(false)
    void queryClient.invalidateQueries({ queryKey: ['twa', 'media', requestNumber] })
    if (sent > 0) toast.success(t('twa.exec.before.uploaded', { count: sent }))
    if (failed > 0) toast.error(t('twa.exec.before.failed', { count: failed }))
  }

  return (
    <div className="bg-white dark:bg-gray-800 rounded-2xl p-4 border border-gray-100 dark:border-gray-700 mb-3 flex flex-col gap-2">
      <p className="text-[12px] text-gray-500 dark:text-gray-400">
        {t('twa.exec.before.count', { count: ids.length, max: BEFORE_PHOTO_LIMIT })}
      </p>
      <input
        ref={inputRef}
        type="file"
        accept="image/*"
        multiple
        className="hidden"
        data-testid="before-input"
        onChange={(e) => {
          const files = Array.from(e.target.files ?? [])
          e.target.value = ''
          if (files.length > 0) void upload(files)
        }}
      />
      {left > 0 && (
        <button
          type="button"
          disabled={busy}
          onClick={() => inputRef.current?.click()}
          className="w-full py-3 rounded-xl text-[13px] font-semibold border border-sky-500 text-sky-600 dark:text-sky-400 flex items-center justify-center gap-2 disabled:opacity-50"
        >
          <Camera size={16} aria-hidden />
          {busy ? t('twa.exec.before.uploading') : t('twa.exec.before.add')}
        </button>
      )}
    </div>
  )
}
