import { useApartmentDetail } from '../../hooks/useAddresses'
import type { ResidentBrief } from '../../types/api'

// -- Styles ---------------------------------------------------------------

const overlayStyle: React.CSSProperties = {
  position: 'fixed', inset: 0, zIndex: 1000,
  background: 'rgba(0,0,0,0.5)',
  display: 'flex', alignItems: 'center', justifyContent: 'center',
}

const panelStyle: React.CSSProperties = {
  background: 'var(--bg-card)',
  border: '1px solid var(--border)',
  borderRadius: 'var(--radius)',
  width: '600px', maxWidth: '90vw', maxHeight: '85vh',
  overflow: 'auto',
  padding: '24px',
}

const headerStyle: React.CSSProperties = {
  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
  marginBottom: 20,
}

const closeBtnStyle: React.CSSProperties = {
  background: 'none', border: 'none', cursor: 'pointer',
  color: 'var(--text-muted)', fontSize: 18, padding: '4px',
}

const infoGridStyle: React.CSSProperties = {
  display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px 24px',
  marginBottom: 24,
}

const infoLabelStyle: React.CSSProperties = {
  fontSize: 12, color: 'var(--text-muted)', marginBottom: 2,
  fontFamily: 'var(--font-display)',
}

const infoValueStyle: React.CSSProperties = {
  fontSize: 13, color: 'var(--text-primary)',
}

const sectionTitleStyle: React.CSSProperties = {
  fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 15,
  color: 'var(--text-primary)', marginBottom: 12,
}

const residentCardStyle: React.CSSProperties = {
  padding: '12px 0',
  borderBottom: '1px solid var(--border)',
}

const badgeBase: React.CSSProperties = {
  fontSize: 10, fontWeight: 600, padding: '2px 7px', borderRadius: 10,
  display: 'inline-block',
}

const footerStyle: React.CSSProperties = {
  display: 'flex', justifyContent: 'flex-end', gap: 8,
  marginTop: 24, paddingTop: 16,
  borderTop: '1px solid var(--border)',
}

const primaryBtnStyle: React.CSSProperties = {
  background: 'var(--accent)', border: 'none', borderRadius: 8,
  cursor: 'pointer', fontSize: 13, color: '#fff', padding: '7px 14px',
  fontFamily: 'var(--font-display)', fontWeight: 600,
}

const secondaryBtnStyle: React.CSSProperties = {
  background: 'var(--bg-card)', border: '1px solid var(--border)',
  borderRadius: 8, cursor: 'pointer', fontSize: 13,
  color: 'var(--text-secondary)', padding: '7px 14px',
  fontFamily: 'var(--font-display)', fontWeight: 500,
}

// -- Helpers --------------------------------------------------------------

function statusBadge(status: string): React.CSSProperties {
  if (status === 'approved') return { ...badgeBase, background: 'rgba(16,185,129,0.15)', color: 'var(--emerald)' }
  if (status === 'rejected') return { ...badgeBase, background: 'rgba(239,68,68,0.15)', color: 'var(--red)' }
  return { ...badgeBase, background: 'rgba(245,158,11,0.15)', color: 'var(--amber)' }
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
      <div style={overlayStyle} onClick={onClose}>
        <div style={panelStyle} onClick={e => e.stopPropagation()}>
          <div style={{ textAlign: 'center', padding: '40px 0', color: 'var(--text-muted)', fontSize: 14 }}>
            Загрузка...
          </div>
        </div>
      </div>
    )
  }

  if (isError || !apartment) {
    return (
      <div style={overlayStyle} onClick={onClose}>
        <div style={panelStyle} onClick={e => e.stopPropagation()}>
          <div style={{ textAlign: 'center', padding: '40px 0', color: 'var(--red)', fontSize: 14 }}>
            Ошибка загрузки
          </div>
        </div>
      </div>
    )
  }

  const residents: ResidentBrief[] = apartment.residents ?? []

  return (
    <div style={overlayStyle} onClick={onClose}>
      <div style={panelStyle} onClick={e => e.stopPropagation()}>
        {/* Header */}
        <div style={headerStyle}>
          <span style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 18, color: 'var(--text-primary)' }}>
            Квартира {apartment.apartment_number}
          </span>
          <button onClick={onClose} style={closeBtnStyle}>&#10005;</button>
        </div>

        {/* Info section */}
        <div style={infoGridStyle}>
          <div>
            <div style={infoLabelStyle}>Адрес</div>
            <div style={infoValueStyle}>{apartment.building_address ?? '—'}</div>
          </div>
          <div>
            <div style={infoLabelStyle}>Двор</div>
            <div style={infoValueStyle}>{apartment.yard_name ?? '—'}</div>
          </div>
          {apartment.entrance != null && (
            <div>
              <div style={infoLabelStyle}>Подъезд</div>
              <div style={infoValueStyle}>{apartment.entrance}</div>
            </div>
          )}
          {apartment.floor != null && (
            <div>
              <div style={infoLabelStyle}>Этаж</div>
              <div style={infoValueStyle}>{apartment.floor}</div>
            </div>
          )}
          {apartment.rooms_count != null && (
            <div>
              <div style={infoLabelStyle}>Комнаты</div>
              <div style={infoValueStyle}>{apartment.rooms_count}</div>
            </div>
          )}
          {apartment.area != null && (
            <div>
              <div style={infoLabelStyle}>Площадь</div>
              <div style={infoValueStyle}>{apartment.area} м&sup2;</div>
            </div>
          )}
          {apartment.description && (
            <div style={{ gridColumn: '1 / -1' }}>
              <div style={infoLabelStyle}>Описание</div>
              <div style={infoValueStyle}>{apartment.description}</div>
            </div>
          )}
          <div>
            <div style={infoLabelStyle}>Статус</div>
            <div>
              <span style={{
                ...badgeBase,
                background: apartment.is_active ? 'rgba(16,185,129,0.15)' : 'rgba(239,68,68,0.15)',
                color: apartment.is_active ? 'var(--emerald)' : 'var(--red)',
              }}>
                {apartment.is_active ? 'Активна' : 'Неактивна'}
              </span>
            </div>
          </div>
        </div>

        {/* Residents section */}
        <div style={sectionTitleStyle}>
          Жители ({residents.length})
        </div>

        {residents.length === 0 ? (
          <div style={{ color: 'var(--text-muted)', fontSize: 13, padding: '12px 0' }}>
            Нет привязанных жителей
          </div>
        ) : (
          <div>
            {residents.map((r, idx) => (
              <div
                key={r.id}
                style={{
                  ...residentCardStyle,
                  borderBottom: idx === residents.length - 1 ? 'none' : '1px solid var(--border)',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                  <span style={{ fontWeight: 600, fontSize: 13, color: 'var(--text-primary)' }}>
                    {r.user_name ?? 'Без имени'}
                  </span>
                  {r.username && (
                    <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                      @{r.username}
                    </span>
                  )}
                </div>

                {r.user_phone && (
                  <div style={{ fontSize: 12, color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)', marginBottom: 6 }}>
                    {r.user_phone}
                  </div>
                )}

                <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
                  {/* Role badge */}
                  <span style={{
                    ...badgeBase,
                    background: r.is_owner ? 'rgba(16,185,129,0.15)' : 'rgba(59,130,246,0.15)',
                    color: r.is_owner ? 'var(--emerald)' : 'var(--blue)',
                  }}>
                    {r.is_owner ? 'Собственник' : 'Жилец'}
                  </span>

                  {/* Status badge */}
                  <span style={statusBadge(r.status)}>
                    {statusLabel(r.status)}
                  </span>

                  {/* Dates */}
                  <span style={{ fontSize: 11, color: 'var(--text-muted)', marginLeft: 'auto' }}>
                    Заявка: {formatDate(r.requested_at)}
                    {r.reviewed_at && <> | Рассмотрена: {formatDate(r.reviewed_at)}</>}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Footer */}
        <div style={footerStyle}>
          <button onClick={onEdit} style={primaryBtnStyle}>Редактировать</button>
          <button onClick={onClose} style={secondaryBtnStyle}>Закрыть</button>
        </div>
      </div>
    </div>
  )
}
