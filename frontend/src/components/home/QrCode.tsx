import { useMemo } from 'react'
import qrcode from 'qrcode-generator'

interface QrCodeProps {
  value: string
  label: string
}

// QR рисуется SVG-путём из матрицы модулей: без innerHTML и без data:-URL
// (CSP img-src), чёткий на любом размере. Тихая зона — 2 модуля, белый фон.
const QUIET = 2

export default function QrCode({ value, label }: QrCodeProps) {
  const { size, path } = useMemo(() => {
    const qr = qrcode(0, 'M')
    qr.addData(value)
    qr.make()
    const count = qr.getModuleCount()
    const parts: string[] = []
    for (let row = 0; row < count; row += 1) {
      for (let col = 0; col < count; col += 1) {
        if (qr.isDark(row, col)) parts.push(`M${col + QUIET} ${row + QUIET}h1v1h-1z`)
      }
    }
    return { size: count + QUIET * 2, path: parts.join('') }
  }, [value])

  return (
    <svg viewBox={`0 0 ${size} ${size}`} role="img" aria-label={label} shapeRendering="crispEdges">
      <rect width={size} height={size} fill="#fff" />
      <path d={path} fill="#1f2a1d" />
    </svg>
  )
}
