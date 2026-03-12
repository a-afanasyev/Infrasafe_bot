import { useState } from 'react'
import { useCreateBuilding, useUpdateBuilding } from '../../hooks/useAddresses'
import type { BuildingBrief, YardBrief } from '../../types/api'

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

const selectStyle: React.CSSProperties = {
  ...inputStyle,
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
  building?: BuildingBrief
  yardId: number
  yards: YardBrief[]
  onClose: () => void
}

export default function BuildingFormModal({ building, yardId, yards, onClose }: Props) {
  const [selectedYardId, setSelectedYardId] = useState(building?.yard_id ?? yardId)
  const [address, setAddress] = useState(building?.address ?? '')
  const [entranceCount, setEntranceCount] = useState(building?.entrance_count ?? 1)
  const [floorCount, setFloorCount] = useState(building?.floor_count ?? 1)
  const [description, setDescription] = useState(building?.description ?? '')
  const [gpsLat, setGpsLat] = useState<string>(building?.gps_latitude != null ? String(building.gps_latitude) : '')
  const [gpsLon, setGpsLon] = useState<string>(building?.gps_longitude != null ? String(building.gps_longitude) : '')

  const createBuilding = useCreateBuilding()
  const updateBuilding = useUpdateBuilding()
  const mutation = building ? updateBuilding : createBuilding

  const handleSubmit = () => {
    if (!address.trim()) return

    const lat = gpsLat ? parseFloat(gpsLat) : null
    const lon = gpsLon ? parseFloat(gpsLon) : null

    if (lat != null && (isNaN(lat) || lat < -90 || lat > 90)) return
    if (lon != null && (isNaN(lon) || lon < -180 || lon > 180)) return

    const payload = {
      address: address.trim(),
      yard_id: selectedYardId,
      entrance_count: entranceCount,
      floor_count: floorCount,
      description: description.trim() || null,
      gps_latitude: lat,
      gps_longitude: lon,
    }

    if (building) {
      updateBuilding.mutate(
        { id: building.id, ...payload },
        { onSuccess: onClose },
      )
    } else {
      createBuilding.mutate(
        { ...payload, is_active: true },
        { onSuccess: onClose },
      )
    }
  }

  return (
    <div onClick={onClose} style={overlayStyle}>
      <div onClick={e => e.stopPropagation()} style={panelStyle}>
        {/* Header */}
        <div style={headerStyle}>
          <span>{building ? 'Редактировать здание' : 'Новое здание'}</span>
          <button onClick={onClose} style={closeBtnStyle}>&#10005;</button>
        </div>

        {/* Body */}
        <div style={bodyStyle}>
          <div>
            <label style={labelStyle}>Двор *</label>
            <select
              value={selectedYardId}
              onChange={e => setSelectedYardId(Number(e.target.value))}
              style={selectStyle}
            >
              {yards.map(y => (
                <option key={y.id} value={y.id}>{y.name}</option>
              ))}
            </select>
          </div>

          <div>
            <label style={labelStyle}>Адрес *</label>
            <input
              value={address}
              onChange={e => setAddress(e.target.value)}
              style={inputStyle}
              autoFocus
            />
          </div>

          <div style={{ display: 'flex', gap: 12 }}>
            <div style={{ flex: 1 }}>
              <label style={labelStyle}>Подъезды</label>
              <input
                type="number"
                value={entranceCount}
                onChange={e => setEntranceCount(Math.max(1, parseInt(e.target.value) || 1))}
                min={1}
                style={inputStyle}
              />
            </div>
            <div style={{ flex: 1 }}>
              <label style={labelStyle}>Этажи</label>
              <input
                type="number"
                value={floorCount}
                onChange={e => setFloorCount(Math.max(1, parseInt(e.target.value) || 1))}
                min={1}
                style={inputStyle}
              />
            </div>
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
              {(mutation.error as any)?.response?.data?.detail || (mutation.error as Error).message || 'Ошибка при сохранении'}
            </div>
          )}
        </div>

        {/* Footer */}
        <div style={footerStyle}>
          <button onClick={onClose} style={cancelBtnStyle}>Отмена</button>
          <button
            onClick={handleSubmit}
            disabled={mutation.isPending || !address.trim()}
            style={{
              ...submitBtnStyle,
              opacity: mutation.isPending || !address.trim() ? 0.6 : 1,
              cursor: mutation.isPending || !address.trim() ? 'not-allowed' : 'pointer',
            }}
          >
            {mutation.isPending ? 'Сохранение...' : building ? 'Сохранить' : 'Создать'}
          </button>
        </div>
      </div>
    </div>
  )
}
