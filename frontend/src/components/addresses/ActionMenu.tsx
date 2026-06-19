import { useEffect, useRef, useState } from 'react'
import { cn } from '@/lib/utils'

// Dropdown-меню действий с закрытием по клику вне (FE-09: вынесено из
// AddressesPage, используется YardGrid/BuildingGrid/ApartmentGrid).

export function ActionMenu({ children }: { children: (close: () => void) => React.ReactNode }) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  return (
    <div ref={ref} className="relative">
      <button
        onClick={(e) => { e.stopPropagation(); setOpen(o => !o) }}
        className="bg-transparent border-none cursor-pointer text-text-muted text-lg px-1.5 py-0.5 leading-none rounded-sm hover:bg-bg-surface"
      >
        ...
      </button>
      {open && (
        <div className="absolute top-full right-0 mt-1 bg-bg-surface border border-border-default rounded-default shadow-[0_8px_24px_rgba(0,0,0,0.25)] z-10 min-w-[160px] overflow-hidden">
          {children(() => setOpen(false))}
        </div>
      )}
    </div>
  )
}

export function MenuItem({ label, onClick, danger }: { label: string; onClick: () => void; danger?: boolean }) {
  return (
    <button
      onClick={(e) => { e.stopPropagation(); onClick() }}
      className={cn(
        'w-full bg-transparent border-none cursor-pointer py-2 px-3.5 text-left text-[13px] font-[family-name:var(--font-display)] block hover:bg-bg-card',
        danger ? 'text-red' : 'text-text-primary'
      )}
    >
      {label}
    </button>
  )
}
