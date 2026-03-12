import { useState } from 'react'
import { useCreateYard, useUpdateYard } from '../../hooks/useAddresses'
import type { YardBrief } from '../../types/api'

// ── Styles ───────────────────────────────────────────────────────────

const overlayStyle: React.CSSProperties = {
  position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)',
  display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000,
}

const panelStyle: React.CSSProperties = {
  background: 'var(--bg-card)', border: '1px solid var(--border)',
  borderRadius: 'var(--radius)', width: 480, maxHeight: '85vh',
  display: 'flex', flexDirection: 'column',
}

const headerStyle: React.CSSProperties = {
  padding: '16px 20px', borderBottom: '1px solid var(--border)',
  fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 15,
  color: 'var(--text-primary)', display: 'flex', justifyContent: 'space-between', alignItems: 'center',
}

const closeBtnStyle: React.CSSProperties = {
  background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)',
  fontSize: 18, padding: '4px',
}

const bodyStyle: React.CSSProperties = {
  padding: '20px', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 16,
}

const footerStyle: React.CSSProperties = {
  padding: '16px 20px', borderTop: '1px solid var(--border)',
  display: 'flex', justifyContent: 'flex-end', gap: 8,
}

const labelStyle: React.CSSProperties = {
  fontSize: 12, color: 'var(--text-muted)', marginBottom: 4, display: 'block',
  fontFamily: 'var(--font-display)',
}

const inputStyle: React.CSSProperties = {
  width: '100%', padding: '8px 12px', background: 'var(--bg-surface)',
  border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)',
  color: 'var(--text-primary)', fontSize: 13, outline: 'none',
  fontFamily: 'var(--font-display)', boxSizing: 'border-box',
}

const textareaStyle: React.CSSProperties = {
  ...inputStyle,
  resize: 'vertical', minHeight: 60,
}

const cancelBtnStyle: React.CSSProperties = {
  background: 'var(--bg-card)', border: '1px solid var(--border)',
  borderRadius: 8, cursor: 'pointer', fontSize: 13,
  color: 'var(--text-secondary)', padding: '7px 14px',
  fontFamily: 'var(--font-display)', fontWeight: 500,
}

const submitBtnStyle: React.CSSProperties = {
  background: 'var(--accent)', border: 'none',
  borderRadius: 8, cursor: 'pointer', fontSize: 13,
  color: '#fff', padding: '7px 14px',
  fontFamily: 'var(--font-display)', fontWeight: 600,
}

// ── Component ────────────────────────────────────────────────────────

interface Props {
  yard?: YardBrief
  onClose: () => void
}

export default function YardFormModal({ yard, onClose }: Props) {
  const [name, setName] = useState(yard?.name ?? '')
  const [description, setDescription] = useState(yard?.description ?? '')
  const [gpsLat, setGpsLat] = useState<string>(yard?.gps_latitude != null ? String(yard.gps_latitude) : '')
  const [gpsLon, setGpsLon] = useState<string>(yard?.gps_longitude != null ? String(yard.gps_longitude) : '')

  const createYard = useCreateYard()
  const updateYard = useUpdateYard()
  const mutation = yard ? updateYard : createYard

  const handleSubmit = () => {
    if (!name.trim()) return

    const lat = gpsLat ? parseFloat(gpsLat) : null
    const lon = gpsLon ? parseFloat(gpsLon) : null

    if (lat != null && (isNaN(lat) || lat < -90 || lat > 90)) return
    if (lon != null && (isNaN(lon) || lon < -180 || lon > 180)) return

    if (yard) {
      updateYard.mutate(
        { id: yard.id, name: name.trim(), description: description.trim() || null, gps_latitude: lat, gps_longitude: lon },
        { onSuccess: onClose },
      )
    } else {
      createYard.mutate(
        { name: name.trim(), description: description.trim() || null, gps_latitude: lat, gps_longitude: lon, is_active: true },
        { onSuccess: onClose },
      )
    }
  }

  return (
    <div onClick={onClose} style={overlayStyle}>
      <div onClick={e => e.stopPropagation()} style={panelStyle}>
        {/* Header */}
        <div style={headerStyle}>
          <span>{yard ? 'Редактировать двор' : 'Новый двор'}</span>
          <button onClick={onClose} style={closeBtnStyle}>&#10005;</button>
        </div>

        {/* Body */}
        <div style={bodyStyle}>
          <div>
            <label style={labelStyle}>Название *</label>
            <input
              value={name}
              onChange={e => setName(e.target.value)}
              style={inputStyle}
              autoFocus
            />
          </div>

          <div>
            <label style={labelStyle}>Описание</label>
            <textarea
              value={description}
              onChange={e => setDescription(e.target.value)}
              style={textareaStyle}
            />
          </div>

          <div style={{ display: 'flex', gap: 12 }}>
            <div style={{ flex: 1 }}>
              <label style={labelStyle}>GPS Широта</label>
              <input
                type="number"
                value={gpsLat}
                onChange={e => setGpsLat(e.target.value)}
                placeholder="-90 ... 90"
                style={inputStyle}
              />
            </div>
            <div style={{ flex: 1 }}>
              <label style={labelStyle}>GPS Долгота</label>
              <input
                type="number"
                value={gpsLon}
                onChange={e => setGpsLon(e.target.value)}
                placeholder="-180 ... 180"
                style={inputStyle}
              />
            </div>
          </div>

          {mutation.error && (
            <div style={{ color: 'var(--red, #ef4444)', fontSize: 13, fontFamily: 'var(--font-display)' }}>
              {(mutation.error as Error).message || 'Ошибка при сохранении'}
            </div>
          )}
        </div>

        {/* Footer */}
        <div style={footerStyle}>
          <button onClick={onClose} style={cancelBtnStyle}>Отмена</button>
          <button
            onClick={handleSubmit}
            disabled={mutation.isPending || !name.trim()}
            style={{
              ...submitBtnStyle,
              opacity: mutation.isPending || !name.trim() ? 0.6 : 1,
              cursor: mutation.isPending || !name.trim() ? 'not-allowed' : 'pointer',
            }}
          >
            {mutation.isPending ? 'Сохранение...' : yard ? 'Сохранить' : 'Создать'}
          </button>
        </div>
      </div>
    </div>
  )
}
