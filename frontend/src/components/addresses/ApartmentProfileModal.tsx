import { useApartmentDetail } from '../../hooks/useAddresses'
import type { ResidentBrief } from '../../types/api'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

// -- Helpers --------------------------------------------------------------

function statusBadgeClass(status: string): string {
  if (status === 'approved') return 'bg-emerald/15 text-emerald'
  if (status === 'rejected') return 'bg-red/15 text-red'
  return 'bg-amber/15 text-amber'
}

function statusLabel(status: string): string {
  if (status === 'approved') return 'Одобрен'
  if (status === 'rejected') return 'Отклонён'
  return 'На рассмотрении'
}

function formatDate(iso: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString('ru-RU')
}

// -- Component ------------------------------------------------------------

interface Props {
  apartmentId: number
  onClose: () => void
  onEdit: () => void
}

export default function ApartmentProfileModal({ apartmentId, onClose, onEdit }: Props) {
  const { data: apartment, isLoading, isError } = useApartmentDetail(apartmentId)

  if (isLoading) {
    return (
      <Dialog open onOpenChange={(open) => { if (!open) onClose() }}>
        <DialogContent className="max-w-[600px]">
          <div className="text-center py-10 text-text-muted text-sm">
            Загрузка...
          </div>
        </DialogContent>
      </Dialog>
    )
  }

  if (isError || !apartment) {
    return (
      <Dialog open onOpenChange={(open) => { if (!open) onClose() }}>
        <DialogContent className="max-w-[600px]">
          <div className="text-center py-10 text-red text-sm">
            Ошибка загрузки
          </div>
        </DialogContent>
      </Dialog>
    )
  }

  const residents: ResidentBrief[] = apartment.residents ?? []

  return (
    <Dialog open onOpenChange={(open) => { if (!open) onClose() }}>
      <DialogContent className="max-w-[600px]">
        <DialogHeader>
          <DialogTitle className="text-lg">
            Квартира {apartment.apartment_number}
          </DialogTitle>
        </DialogHeader>

        {/* Info section */}
        <div className="grid grid-cols-2 gap-x-6 gap-y-3 mb-6">
          <div>
            <div className="text-xs text-text-muted font-[family-name:var(--font-display)] mb-0.5">Адрес</div>
            <div className="text-[13px] text-text-primary">{apartment.building_address ?? '—'}</div>
          </div>
          <div>
            <div className="text-xs text-text-muted font-[family-name:var(--font-display)] mb-0.5">Двор</div>
            <div className="text-[13px] text-text-primary">{apartment.yard_name ?? '—'}</div>
          </div>
          {apartment.entrance != null && (
            <div>
              <div className="text-xs text-text-muted font-[family-name:var(--font-display)] mb-0.5">Подъезд</div>
              <div className="text-[13px] text-text-primary">{apartment.entrance}</div>
            </div>
          )}
          {apartment.floor != null && (
            <div>
              <div className="text-xs text-text-muted font-[family-name:var(--font-display)] mb-0.5">Этаж</div>
              <div className="text-[13px] text-text-primary">{apartment.floor}</div>
            </div>
          )}
          {apartment.rooms_count != null && (
            <div>
              <div className="text-xs text-text-muted font-[family-name:var(--font-display)] mb-0.5">Комнаты</div>
              <div className="text-[13px] text-text-primary">{apartment.rooms_count}</div>
            </div>
          )}
          {apartment.area != null && (
            <div>
              <div className="text-xs text-text-muted font-[family-name:var(--font-display)] mb-0.5">Площадь</div>
              <div className="text-[13px] text-text-primary">{apartment.area} м&sup2;</div>
            </div>
          )}
          {apartment.description && (
            <div className="col-span-2">
              <div className="text-xs text-text-muted font-[family-name:var(--font-display)] mb-0.5">Описание</div>
              <div className="text-[13px] text-text-primary">{apartment.description}</div>
            </div>
          )}
          <div>
            <div className="text-xs text-text-muted font-[family-name:var(--font-display)] mb-0.5">Статус</div>
            <div>
              <span className={cn(
                'text-[10px] font-semibold px-[7px] py-0.5 rounded-[10px] inline-block',
                apartment.is_active ? 'bg-emerald/15 text-emerald' : 'bg-red/15 text-red'
              )}>
                {apartment.is_active ? 'Активна' : 'Неактивна'}
              </span>
            </div>
          </div>
        </div>

        {/* Residents section */}
        <div className="font-[family-name:var(--font-display)] font-bold text-[15px] text-text-primary mb-3">
          Жители ({residents.length})
        </div>

        {residents.length === 0 ? (
          <div className="text-text-muted text-[13px] py-3">
            Нет привязанных жителей
          </div>
        ) : (
          <div>
            {residents.map((r, idx) => (
              <div
                key={r.id}
                className={cn(
                  'py-3',
                  idx !== residents.length - 1 && 'border-b border-border-default'
                )}
              >
                <div className="flex items-center gap-2 mb-1">
                  <span className="font-semibold text-[13px] text-text-primary">
                    {r.user_name ?? 'Без имени'}
                  </span>
                  {r.username && (
                    <span className="text-xs text-text-muted">
                      @{r.username}
                    </span>
                  )}
                </div>

                {r.user_phone && (
                  <div className="text-xs text-text-secondary font-[family-name:var(--font-mono)] mb-1.5">
                    {r.user_phone}
                  </div>
                )}

                <div className="flex items-center gap-1.5 flex-wrap">
                  {/* Role badge */}
                  <span className={cn(
                    'text-[10px] font-semibold px-[7px] py-0.5 rounded-[10px] inline-block',
                    r.is_owner ? 'bg-emerald/15 text-emerald' : 'bg-blue/15 text-blue'
                  )}>
                    {r.is_owner ? 'Собственник' : 'Жилец'}
                  </span>

                  {/* Status badge */}
                  <span className={cn(
                    'text-[10px] font-semibold px-[7px] py-0.5 rounded-[10px] inline-block',
                    statusBadgeClass(r.status)
                  )}>
                    {statusLabel(r.status)}
                  </span>

                  {/* Dates */}
                  <span className="text-[11px] text-text-muted ml-auto">
                    Заявка: {formatDate(r.requested_at)}
                    {r.reviewed_at && <> | Рассмотрена: {formatDate(r.reviewed_at)}</>}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}

        <DialogFooter>
          <Button onClick={onEdit}>Редактировать</Button>
          <Button variant="outline" onClick={onClose}>Закрыть</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
