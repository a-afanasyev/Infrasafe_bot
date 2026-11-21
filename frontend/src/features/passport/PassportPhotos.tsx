import { useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import { apiClient } from '../../api/client'
import { fetchFileAsDataUrl } from '../../api/fileDataUrl'
import { PASSPORTS_BASE, passportErrorCode, passportKeys, uploadPassportPhoto, type PassportPhoto } from './api'

/**
 * Фото раздела паспорта: сетка превью, добавление и удаление.
 * Превью — data: URL (CSP не пускает blob:). Загрузка идёт с ключом операции:
 * повтор после обрыва или «ещё выполняется» не создаёт второго файла.
 */
interface Props {
  buildingId: number
  section: string
  photos: PassportPhoto[]
  canEdit: boolean
}

function Thumb({ buildingId, photo, onRemove }: { buildingId: number; photo: PassportPhoto; onRemove?: () => void }) {
  const { t } = useTranslation()
  const url = `${PASSPORTS_BASE}/buildings/${buildingId}/photos/${photo.id}/file`
  const preview = useQuery({ queryKey: ['passport-photo', buildingId, photo.id], queryFn: () => fetchFileAsDataUrl(url), staleTime: Infinity })
  const [full, setFull] = useState<string | null>(null)
  const openOriginal = async () => setFull((await fetchFileAsDataUrl(`${url}?original=true`)).dataUrl)
  return (
    <div className="relative h-24 w-24 overflow-hidden rounded-sm border border-border-default bg-bg-surface">
      {preview.data && (
        <button type="button" className="h-full w-full" onClick={openOriginal} aria-label={t('housePassport.photos.open')}>
          <img src={preview.data.dataUrl} alt={photo.uploaded_by_name ?? ''} className="h-full w-full object-cover" />
        </button>
      )}
      {full && (
        <button type="button" className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4"
                aria-label={t('common.close')} onClick={() => setFull(null)}>
          <img src={full} alt="" className="max-h-full max-w-full" />
        </button>
      )}
      {onRemove && (
        <button type="button" className="absolute right-0 top-0 bg-bg-card px-1.5 text-sm text-text-primary"
                aria-label={t('housePassport.photos.remove')} onClick={onRemove}>×</button>
      )}
    </div>
  )
}

export default function PassportPhotos({ buildingId, section, photos, canEdit }: Props) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const input = useRef<HTMLInputElement>(null)
  const refresh = () => qc.invalidateQueries({ queryKey: passportKeys.detail(buildingId) })
  const onError = (error: unknown) =>
    toast.error(t(`housePassport.errors.${passportErrorCode(error) ?? 'generic'}`, { defaultValue: t('housePassport.errors.generic') }))

  const add = useMutation({
    mutationFn: async (files: File[]) => { for (const file of files) await uploadPassportPhoto(buildingId, section, file) },
    onError,
    onSettled: refresh,
  })
  const remove = useMutation({
    mutationFn: (id: number) => apiClient.delete(`${PASSPORTS_BASE}/buildings/${buildingId}/photos/${id}`),
    onError,
    onSettled: refresh,
  })

  if (!canEdit && photos.length === 0) return null
  return (
    <div className="flex flex-wrap items-center gap-2">
      {photos.map((photo) => (
        <Thumb key={photo.id} buildingId={buildingId} photo={photo} onRemove={canEdit ? () => remove.mutate(photo.id) : undefined} />
      ))}
      {canEdit && (
        <>
          <input ref={input} type="file" accept="image/jpeg,image/png" multiple hidden aria-label={t('housePassport.photos.add')}
                 onChange={(e) => { add.mutate(Array.from(e.target.files ?? [])); e.target.value = '' }} />
          <Button variant="outline" size="sm" disabled={add.isPending} onClick={() => input.current?.click()}>
            {add.isPending ? t('housePassport.photos.uploading') : t('housePassport.photos.add')}
          </Button>
        </>
      )}
    </div>
  )
}
