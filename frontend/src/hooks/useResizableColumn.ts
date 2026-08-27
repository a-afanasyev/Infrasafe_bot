import { useCallback, useRef, useState } from 'react'
import type { PointerEvent as ReactPointerEvent } from 'react'

/**
 * Ширина колонки, которую пользователь тянет за правую кромку.
 *
 * Родился из жалобы владельца на расписание смен: колонка «Исполнитель» в
 * 180px обрезала ФИО, а прочитать их целиком было негде. Ширина живёт в
 * localStorage — настройка переживает перезагрузку и общая для всех вью,
 * использующих один storageKey (месяц и неделя выглядят согласованно).
 *
 * Drag — pointer-события с capture на самой ручке: mousemove за пределами
 * ручки продолжает тянуть, отпускание где угодно завершает.
 */
export function useResizableColumn(
  storageKey: string,
  defaultWidth: number,
  min = 140,
  max = 440,
) {
  const [width, setWidth] = useState<number>(() => {
    const saved = Number(localStorage.getItem(storageKey))
    return Number.isFinite(saved) && saved >= min && saved <= max ? saved : defaultWidth
  })
  const drag = useRef<{ startX: number; startW: number } | null>(null)

  const onPointerDown = useCallback(
    (e: ReactPointerEvent<HTMLElement>) => {
      e.preventDefault()
      drag.current = { startX: e.clientX, startW: width }
      e.currentTarget.setPointerCapture(e.pointerId)
    },
    [width],
  )

  const onPointerMove = useCallback(
    (e: ReactPointerEvent<HTMLElement>) => {
      if (!drag.current) return
      const next = Math.min(max, Math.max(min, drag.current.startW + e.clientX - drag.current.startX))
      setWidth(next)
    },
    [min, max],
  )

  const onPointerUp = useCallback(() => {
    if (!drag.current) return
    drag.current = null
    setWidth(w => {
      localStorage.setItem(storageKey, String(w))
      return w
    })
  }, [storageKey])

  return {
    width,
    /** Развесить на элемент-ручку (правая кромка колонки). */
    handleProps: { onPointerDown, onPointerMove, onPointerUp, onPointerCancel: onPointerUp },
  }
}
