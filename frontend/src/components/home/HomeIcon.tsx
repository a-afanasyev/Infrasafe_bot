// Линейные иконки страницы жителей (24×24, stroke = currentColor). Свой набор,
// а не lucide: рисунок макета тоньше и с другими пропорциями, и страница
// должна выглядеть одинаково в обоих брендах.

const PATHS = {
  arrow: <path d="M5 12h14m-6-6 6 6-6 6" />,
  upRight: <path d="M6 18 18 6M6 6h12v12" />,
  chevron: <path d="m9 5 7 7-7 7" />,
  building: <path d="M4 21V6l10-3v18M14 9h6v12M2 21h20M8 9h2m-2 4h2m-2 4h2m7-4h1m-1 4h1" />,
  monitor: (
    <>
      <rect x="3" y="4" width="18" height="13" rx="2" />
      <path d="M8 21h8m-4-4v4" />
    </>
  ),
  phone: <path d="M8.5 3 11 8l-3 2c1 3 3 5 6 6l2-3 5 2.5v3.7a1.8 1.8 0 0 1-2 1.8C10 20 4 14 3 5a1.8 1.8 0 0 1 1.8-2Z" />,
  telegram: (
    <>
      <path d="m21 3-4 18-6-6-4 3 1-6-5-2 18-7Z" />
      <path d="m8 12 9-5-6 8" />
    </>
  ),
  calendar: (
    <>
      <rect x="3" y="5" width="18" height="16" rx="2" />
      <path d="M7 3v4m10-4v4M3 11h18M7 15h3m4 0h3m-10 3h3" />
    </>
  ),
  clock: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3 2" />
    </>
  ),
  pause: <path d="M9 5v14M15 5v14" />,
  play: <path d="m8 5 11 7-11 7Z" />,
  close: <path d="m6 6 12 12M18 6 6 18" />,
  leaf: (
    <>
      <path d="M20 3S5 2 4 12c-.5 5 4 8 8 6 7-3 8-15 8-15Z" />
      <path d="M4 21 15 9" />
    </>
  ),
  notice: <path d="m3 10 15-6v16L3 14v-4Zm4 6 1 5h3l-2-5m12-7v6" />,
  info: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 11v6m0-10v1" />
    </>
  ),
  grid: (
    <>
      <rect x="3" y="3" width="7" height="7" rx="1" />
      <rect x="14" y="3" width="7" height="7" rx="1" />
      <rect x="3" y="14" width="7" height="7" rx="1" />
      <rect x="14" y="14" width="7" height="7" rx="1" />
    </>
  ),
  alert: (
    <>
      <path d="M12 3 2 20h20L12 3Z" />
      <path d="M12 10v4m0 3v.5" />
    </>
  ),
} as const

export type HomeIconName = keyof typeof PATHS

interface HomeIconProps {
  name: HomeIconName
  className?: string
}

export default function HomeIcon({ name, className }: HomeIconProps) {
  return (
    <svg className={className ? `rh-icon ${className}` : 'rh-icon'} viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      {PATHS[name]}
    </svg>
  )
}
