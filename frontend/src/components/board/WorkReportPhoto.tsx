import { useState } from 'react'

// Shared between WorkReportsModule.tsx (compact board-widget preview) and
// pages/WorkReportsArchivePage.tsx (full public archive) — extracted per T12
// code review: unlike the cardStyle/headerStyle/titleStyle literals still
// duplicated between ResidentBoardPage.tsx/WorkReportsModule.tsx (inert CSS,
// low risk if they drift), this component is actual BEHAVIOR (state, onError
// fallback, placeholder rendering) — duplicating it means a future fix has to
// be remembered in two places. Per-context visual tuning (box border-radius,
// placeholder font-size/padding) stays local to each consumer via the
// boxStyle/placeholderStyle props.

export interface WorkReportPhotoProps {
  // undefined when the report is (defensively) missing a before/after media
  // id — render the placeholder directly, never pass undefined into
  // publicWorkReportMediaUrl.
  src?: string
  alt: string
  // Container style (aspect-ratio/border-radius/overflow/background) — tuned
  // per consumer (e.g. compact board tiles vs roomier archive cards).
  boxStyle: React.CSSProperties
  // Extra style merged onto the placeholder only (font-size/padding), applied
  // on top of boxStyle — also tuned per consumer.
  placeholderStyle?: React.CSSProperties
  // Текст плейсхолдера. Отдельно от `alt`, потому что смысл разный: alt — это
  // «До»/«После» (какая сторона), а здесь нужно сказать, что снимка нет.
  // Отчёт без фото «до» — штатное состояние с 2026-07-25: обязателен только
  // результат, и витрина честно показывает «нет фото» вместо пустой плитки.
  emptyLabel?: string
}

export default function WorkReportPhoto({
  src, alt, boxStyle, placeholderStyle, emptyLabel,
}: WorkReportPhotoProps) {
  const [failed, setFailed] = useState(false)
  if (!src || failed) {
    return (
      <div
        style={{
          ...boxStyle,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: '#9ca3af',
          fontWeight: 600,
          textAlign: 'center',
          ...placeholderStyle,
        }}
      >
        {emptyLabel || alt}
      </div>
    )
  }
  return (
    <div style={boxStyle}>
      <img
        src={src}
        alt={alt}
        loading="lazy"
        decoding="async"
        onError={() => setFailed(true)}
        style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }}
      />
    </div>
  )
}
