import type { ZoneRef } from '../../types/access'

/**
 * Чекбокс-список зон парковки (кандидаты — обслуживающие зоны адреса). Режим
 * `multi` — несколько зон (авто/заявка); `single` — ровно одна (пропуск): выбор
 * одной снимает прочие. Пустой список кандидатов → подсказка `emptyText`.
 */
interface Props {
  zones: ZoneRef[]
  selected: number[]
  onChange: (ids: number[]) => void
  mode?: 'multi' | 'single'
  emptyText?: string
}

function zoneLabel(z: ZoneRef): string {
  return z.name || z.code || `#${z.id}`
}

export default function ZoneCheckboxes({
  zones,
  selected,
  onChange,
  mode = 'multi',
  emptyText,
}: Props) {
  if (zones.length === 0) {
    return <p className="text-[13px] text-text-muted">{emptyText ?? '—'}</p>
  }

  const toggle = (id: number, checked: boolean) => {
    if (mode === 'single') {
      onChange(checked ? [id] : [])
      return
    }
    onChange(checked ? [...selected, id] : selected.filter((x) => x !== id))
  }

  return (
    <div className="flex flex-col gap-2">
      {zones.map((z) => (
        <label
          key={z.id}
          className="flex items-center gap-2 text-[13px] text-text-primary cursor-pointer"
        >
          <input
            type="checkbox"
            checked={selected.includes(z.id)}
            onChange={(e) => toggle(z.id, e.target.checked)}
            className="h-4 w-4 accent-accent"
          />
          <span>{zoneLabel(z)}</span>
          {z.code && z.name && (
            <span className="text-[12px] text-text-muted">({z.code})</span>
          )}
        </label>
      ))}
    </div>
  )
}
