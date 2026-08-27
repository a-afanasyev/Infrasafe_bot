import { useCallback, useRef, useState } from 'react'
import type { PointerEvent as ReactPointerEvent } from 'react'

/**
 * Ширина колонки, которую пользователь тянет за правую кромку.
 *
 * Родился из жалобы владельца на расписание смен: колонка «Исполнитель»
 * обрезала ФИО, а прочитать их целиком было негде. Явно выбранная ширина
 * живёт в localStorage — настройка переживает перезагрузку и общая для всех
 * вью с одним storageKey (месяц и неделя выглядят согласованно).
 *
 * `autoWidth` — автоподбор под контент (например, самое длинное ФИО):
 * пока пользователь НЕ трогал колонку (нет сохранённой ширины и не тянул в
 * этой сессии), показывается clamp(autoWidth); первый же drag фиксирует
 * ручное управление. Так ФИО читаемы «из коробки», а ручка остаётся.
 *
 * Drag — pointer-события с capture на самой ручке: mousemove за пределами
 * ручки продолжает тянуть, отпускание где угодно завершает.
 */
export function useResizableColumn(
  storageKey: string,
  defaultWidth: number,
  min = 140,
  max = 440,
  autoWidth?: number,
) {
  const [manualWidth, setManualWidth] = useState<number>(() => {
    const saved = Number(localStorage.getItem(storageKey))
    return Number.isFinite(saved) && saved >= min && saved <= max ? saved : defaultWidth
  })
  // Пользователь ЯВНО управлял шириной (сохранённая или drag в сессии)?
  // Пока нет — действует автоподбор под контент.
  const [touched, setTouched] = useState<boolean>(
    () => localStorage.getItem(storageKey) !== null,
  )
  const drag = useRef<{ startX: number; startW: number } | null>(null)

  const clamp = (v: number) => Math.min(max, Math.max(min, v))
  const width =
    touched || autoWidth === undefined ? manualWidth : clamp(autoWidth)

  const onPointerDown = useCallback(
    (e: ReactPointerEvent<HTMLElement>) => {
      e.preventDefault()
      // Базой драга служит ВИДИМАЯ ширина (может быть автоподобранной) —
      // иначе первый рывок прыгал бы к прежнему manualWidth.
      drag.current = { startX: e.clientX, startW: width }
      setManualWidth(width)
      setTouched(true)
      e.currentTarget.setPointerCapture(e.pointerId)
    },
    [width],
  )

  const onPointerMove = useCallback(
    (e: ReactPointerEvent<HTMLElement>) => {
      if (!drag.current) return
      const next = clamp(drag.current.startW + e.clientX - drag.current.startX)
      setManualWidth(next)
    },
    // clamp зависит только от min/max
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [min, max],
  )

  const onPointerUp = useCallback(() => {
    if (!drag.current) return
    drag.current = null
    setManualWidth(w => {
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
