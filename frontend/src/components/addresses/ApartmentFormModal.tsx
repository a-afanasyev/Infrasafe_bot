import { useState } from 'react'
import { useCreateApartment, useUpdateApartment } from '../../hooks/useAddresses'
import type { ApartmentBrief } from '../../types/api'

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
  apartment?: ApartmentBrief
  buildingId: number
  onClose: () => void
}

export default function ApartmentFormModal({ apartment, buildingId, onClose }: Props) {
  const [apartmentNumber, setApartmentNumber] = useState(apartment?.apartment_number ?? '')
  const [entrance, setEntrance] = useState<string>(apartment?.entrance != null ? String(apartment.entrance) : '')
  const [floor, setFloor] = useState<string>(apartment?.floor != null ? String(apartment.floor) : '')
  const [roomsCount, setRoomsCount] = useState<string>(apartment?.rooms_count != null ? String(apartment.rooms_count) : '')
  const [area, setArea] = useState<string>(apartment?.area != null ? String(apartment.area) : '')
  const [description, setDescription] = useState(apartment?.description ?? '')

  const createApartment = useCreateApartment()
  const updateApartment = useUpdateApartment()
  const mutation = apartment ? updateApartment : createApartment

  const handleSubmit = () => {
    if (!apartmentNumber.trim()) return

    const payload = {
      building_id: buildingId,
      apartment_number: apartmentNumber.trim(),
      entrance: entrance ? parseInt(entrance) || null : null,
      floor: floor ? parseInt(floor) || null : null,
      rooms_count: roomsCount ? parseInt(roomsCount) || null : null,
      area: area ? parseFloat(area) || null : null,
      description: description.trim() || null,
    }

    if (apartment) {
      updateApartment.mutate(
        { id: apartment.id, ...payload },
        { onSuccess: onClose },
      )
    } else {
      createApartment.mutate(
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
          <span>{apartment ? 'Редактировать квартиру' : 'Новая квартира'}</span>
          <button onClick={onClose} style={closeBtnStyle}>&#10005;</button>
        </div>

        {/* Body */}
        <div style={bodyStyle}>
          <div>
            <label style={labelStyle}>Номер квартиры *</label>
            <input
              value={apartmentNumber}
              onChange={e => setApartmentNumber(e.target.value)}
              style={inputStyle}
              autoFocus
            />
          </div>

          <div style={{ display: 'flex', gap: 12 }}>
            <div style={{ flex: 1 }}>
              <label style={labelStyle}>Подъезд</label>
              <input
                type="number"
                value={entrance}
                onChange={e => setEntrance(e.target.value)}
                style={inputStyle}
              />
            </div>
            <div style={{ flex: 1 }}>
              <label style={labelStyle}>Этаж</label>
              <input
                type="number"
                value={floor}
                onChange={e => setFloor(e.target.value)}
                style={inputStyle}
              />
            </div>
          </div>

          <div style={{ display: 'flex', gap: 12 }}>
            <div style={{ flex: 1 }}>
              <label style={labelStyle}>Комнаты</label>
              <input
                type="number"
                value={roomsCount}
                onChange={e => setRoomsCount(e.target.value)}
                style={inputStyle}
              />
            </div>
            <div style={{ flex: 1 }}>
              <label style={labelStyle}>Площадь м&sup2;</label>
              <input
                type="number"
                value={area}
                onChange={e => setArea(e.target.value)}
                step="0.1"
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
            disabled={mutation.isPending || !apartmentNumber.trim()}
            style={{
              ...submitBtnStyle,
              opacity: mutation.isPending || !apartmentNumber.trim() ? 0.6 : 1,
              cursor: mutation.isPending || !apartmentNumber.trim() ? 'not-allowed' : 'pointer',
            }}
          >
            {mutation.isPending ? 'Сохранение...' : apartment ? 'Сохранить' : 'Создать'}
          </button>
        </div>
      </div>
    </div>
  )
}
