import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { ResidentDocument } from '../../types/api'
import { apiClient } from '../../api/client'
import { formatDate as fmtDate } from '../../i18n/formatters'
import { Button } from '@/components/ui/button'

interface Props {
  residentId: number
  documents: ResidentDocument[]
}

/** Читаем файл как **data:** URL, а не blob:.
 *
 *  На `/uk/*` действует CSP с `img-src` без `blob:` — превью через
 *  `URL.createObjectURL` там молча не отрисовывается. data: URL проходит.
 *  Цена — файл целиком в памяти вкладки, но документ ограничен 20 МБ лимитом
 *  Telegram, а открывают их по одному.
 */
async function fetchAsDataUrl(url: string): Promise<{ dataUrl: string; type: string }> {
  const response = await apiClient.get(url, { responseType: 'blob' })
  const blob = response.data as Blob
  const dataUrl = await new Promise<string>((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(reader.result as string)
    reader.onerror = () => reject(reader.error)
    reader.readAsDataURL(blob)
  })
  return { dataUrl, type: blob.type }
}

export default function ResidentDocuments({ residentId, documents }: Props) {
  const { t } = useTranslation()
  const [openId, setOpenId] = useState<number | null>(null)
  const [preview, setPreview] = useState<{ dataUrl: string; type: string } | null>(null)
  const [loadingId, setLoadingId] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)

  if (documents.length === 0) {
    return <div className="text-[13px] text-text-muted">{t('residents.noDocuments')}</div>
  }

  const open = async (doc: ResidentDocument) => {
    setLoadingId(doc.id)
    setError(null)
    try {
      const loaded = await fetchAsDataUrl(
        `/api/v2/residents/${residentId}/documents/${doc.id}/file`,
      )
      if (loaded.type.startsWith('image/')) {
        setPreview(loaded)
        setOpenId(doc.id)
      } else {
        // Не изображение (PDF и прочее) — только скачивание: бэкенд и отдаёт
        // такие файлы с Content-Disposition: attachment.
        const link = document.createElement('a')
        link.href = loaded.dataUrl
        link.download = doc.file_name || `document-${doc.id}`
        link.click()
      }
    } catch {
      setError(t('residents.documentLoadFailed'))
    } finally {
      setLoadingId(null)
    }
  }

  return (
    <div className="flex flex-col gap-2">
      {documents.map(d => (
        <div key={d.id} className="border border-border-default rounded-sm p-3 flex flex-col gap-2">
          <div className="flex items-center gap-3 flex-wrap">
            <span className="text-[13px] text-text-primary">
              {t(`residents.documentType.${d.document_type}`, d.document_type)}
            </span>
            {d.file_name && (
              <span className="text-[11px] text-text-muted font-[family-name:var(--font-mono)]">
                {d.file_name}
              </span>
            )}
            {d.created_at && (
              <span className="text-[11px] text-text-muted">
                {fmtDate(d.created_at, { dateStyle: 'short' })}
              </span>
            )}
            <Button
              variant="outline"
              size="sm"
              className="ml-auto"
              disabled={loadingId === d.id}
              onClick={() => open(d)}
            >
              {loadingId === d.id ? t('residents.documentLoading') : t('residents.documentOpen')}
            </Button>
          </div>

          {openId === d.id && preview && (
            <div className="flex flex-col gap-2">
              <img
                src={preview.dataUrl}
                alt={t(`residents.documentType.${d.document_type}`, d.document_type)}
                className="max-w-full rounded-sm border border-border-default"
              />
              <button
                onClick={() => { setOpenId(null); setPreview(null) }}
                className="bg-transparent border-none cursor-pointer text-[13px] text-text-muted underline p-0 w-fit"
              >
                {t('residents.documentClose')}
              </button>
            </div>
          )}
        </div>
      ))}

      {error && <div className="text-[12px] text-red">{error}</div>}
    </div>
  )
}
