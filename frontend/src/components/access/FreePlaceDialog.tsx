import { useTranslation } from 'react-i18next'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import LoadingSpinner from '../shared/LoadingSpinner'
import { useOpenPresenceSessions, useClosePresenceSession } from '../../hooks/useParkingAdmin'

/**
 * Диалог «Освободить место» (§10.3): список ОТКРЫТЫХ presence-сессий квартиры в
 * зоне закрепления; закрытие выбранной (POST /presence/{id}/close) освобождает
 * место — занятость «X из Y» обновляется (invalidate в хуке закрытия).
 *
 * Запрос сессий включается только пока диалог открыт (apartmentId != null).
 */
interface Props {
  apartmentId: number | null
  zoneId: number | null
  onClose: () => void
}

/** Дата ISO → локальная короткая строка. */
function fmt(v: string): string {
  const d = new Date(v)
  return Number.isNaN(d.getTime()) ? v : d.toLocaleString()
}

export default function FreePlaceDialog({ apartmentId, zoneId, onClose }: Props) {
  const { t } = useTranslation()
  const open = apartmentId !== null
  const filters =
    apartmentId !== null
      ? { apartment_id: apartmentId, ...(zoneId !== null ? { zone_id: zoneId } : {}) }
      : undefined
  const { data, isLoading } = useOpenPresenceSessions(filters, open)
  const closeSession = useClosePresenceSession()

  const sessions = data?.items ?? []

  function handleFree(id: number) {
    closeSession.mutate(
      { id, payload: { reason: t('accessControl.parking.freePlace.reason') } },
      { onSuccess: () => onClose() },
    )
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{t('accessControl.parking.freePlace.title')}</DialogTitle>
          <DialogDescription>{t('accessControl.parking.freePlace.desc')}</DialogDescription>
        </DialogHeader>

        {isLoading ? (
          <LoadingSpinner />
        ) : sessions.length === 0 ? (
          <p className="text-[13px] text-text-muted py-2">
            {t('accessControl.parking.freePlace.empty')}
          </p>
        ) : (
          <ul className="flex flex-col gap-2">
            {sessions.map((s) => (
              <li
                key={s.id}
                className="flex items-center justify-between gap-2 rounded-default border border-border-default bg-bg-surface px-3 py-2"
              >
                <div className="min-w-0">
                  <p className="font-mono text-[13px] text-text-primary truncate">
                    {s.plate_normalized ?? `#${s.vehicle_id}`}
                  </p>
                  <p className="text-[11px] text-text-muted">
                    {t('accessControl.parking.freePlace.enteredAt')}: {fmt(s.entered_at)}
                  </p>
                </div>
                <Button
                  size="sm"
                  variant="destructive"
                  disabled={closeSession.isPending}
                  onClick={() => handleFree(s.id)}
                >
                  {t('accessControl.parking.freePlace.confirm')}
                </Button>
              </li>
            ))}
          </ul>
        )}
      </DialogContent>
    </Dialog>
  )
}
