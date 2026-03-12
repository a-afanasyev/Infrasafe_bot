import { useState, useMemo } from 'react'
import { useBulkCreateApartments } from '../../hooks/useAddresses'
import type { BulkCreateResult } from '../../types/api'

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

const textareaStyle: React.CSSProperties = {
  width: '100%', padding: '8px 12px', background: 'var(--bg-surface)',
  border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)',
  color: 'var(--text-primary)', fontSize: 13, outline: 'none',
  fontFamily: 'var(--font-display)', boxSizing: 'border-box',
  resize: 'vertical', minHeight: 80,
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

// ── Parsing ──────────────────────────────────────────────────────────

function parseApartmentRange(input: string): string[] {
  const parts = input.split(',').map(s => s.trim()).filter(Boolean)
  const numbers = new Set<string>()
  for (const part of parts) {
    if (part.includes('-')) {
      const [startStr, endStr] = part.split('-').map(s => s.trim())
      const start = parseInt(startStr, 10)
      const end = parseInt(endStr, 10)
      if (!isNaN(start) && !isNaN(end) && start <= end && end - start < 500) {
        for (let i = start; i <= end; i++) {
          numbers.add(String(i))
        }
      }
    } else {
      numbers.add(part)
    }
  }
  return Array.from(numbers).sort((a, b) => {
    const na = parseInt(a, 10)
    const nb = parseInt(b, 10)
    if (!isNaN(na) && !isNaN(nb)) return na - nb
    return a.localeCompare(b)
  })
}

// ── Component ────────────────────────────────────────────────────────

interface Props {
  buildingId: number
  buildingAddress: string
  onClose: () => void
}

export default function BulkCreateModal({ buildingId, buildingAddress, onClose }: Props) {
  const [input, setInput] = useState('')
  const [result, setResult] = useState<BulkCreateResult | null>(null)

  const bulkCreate = useBulkCreateApartments()

  const parsed = useMemo(() => parseApartmentRange(input), [input])
  const tooMany = parsed.length > 500

  const canSubmit = parsed.length > 0 && !tooMany && !bulkCreate.isPending

  const handleSubmit = () => {
    if (!canSubmit) return
    bulkCreate.mutate(
      { building_id: buildingId, apartment_numbers: parsed },
      { onSuccess: (data) => setResult(data) },
    )
  }

  return (
    <div onClick={onClose} style={overlayStyle}>
      <div onClick={e => e.stopPropagation()} style={panelStyle}>
        {/* Header */}
        <div style={headerStyle}>
          <span>Массовое создание квартир</span>
          <button onClick={onClose} style={closeBtnStyle}>&#10005;</button>
        </div>

        {/* Body */}
        <div style={bodyStyle}>
          <div style={{ fontSize: 13, color: 'var(--text-secondary)', fontFamily: 'var(--font-display)' }}>
            {buildingAddress}
          </div>

          {result ? (
            /* Result summary */
            <>
              <div style={{
                padding: 16,
                background: 'var(--bg-surface)',
                borderRadius: 'var(--radius-sm)',
                border: '1px solid var(--border)',
                display: 'flex',
                flexDirection: 'column',
                gap: 6,
                fontFamily: 'var(--font-display)',
                fontSize: 14,
                color: 'var(--text-primary)',
              }}>
                <div>Создано: {result.created}</div>
                <div>Пропущено (дубли): {result.skipped}</div>
                {result.errors.length > 0 && (
                  <div style={{ color: 'var(--red, #ef4444)' }}>
                    Ошибки: {result.errors.join(', ')}
                  </div>
                )}
              </div>
            </>
          ) : (
            /* Input form */
            <>
              <div>
                <label style={labelStyle}>Номера квартир</label>
                <textarea
                  value={input}
                  onChange={e => setInput(e.target.value)}
                  placeholder="Например: 1-50 или 1, 5, 10, 15-20"
                  style={textareaStyle}
                  autoFocus
                />
              </div>

              {input.trim() && (
                <div style={{
                  fontSize: 13,
                  fontFamily: 'var(--font-display)',
                  color: tooMany ? 'var(--red, #ef4444)' : 'var(--text-secondary)',
                }}>
                  {tooMany
                    ? 'Максимум 500 квартир за раз'
                    : `Будет создано: ${parsed.length} квартир`
                  }
                </div>
              )}

              {bulkCreate.error && (
                <div style={{ color: 'var(--red, #ef4444)', fontSize: 13, fontFamily: 'var(--font-display)' }}>
                  {(bulkCreate.error as Error).message || 'Ошибка при создании'}
                </div>
              )}
            </>
          )}
        </div>

        {/* Footer */}
        <div style={footerStyle}>
          {result ? (
            <button onClick={onClose} style={submitBtnStyle}>
              OK
            </button>
          ) : (
            <>
              <button onClick={onClose} style={cancelBtnStyle}>Отмена</button>
              <button
                onClick={handleSubmit}
                disabled={!canSubmit}
                style={{
                  ...submitBtnStyle,
                  opacity: canSubmit ? 1 : 0.6,
                  cursor: canSubmit ? 'pointer' : 'not-allowed',
                }}
              >
                {bulkCreate.isPending ? 'Создание...' : 'Создать'}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
