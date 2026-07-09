import { useState, useEffect } from 'react'
import { brand } from '../brand/brand'

export function useTheme() {
  // Light-only бренд (PROFK) держит светлую тему принудительно, игнорируя
  // localStorage и toggle; тумблер темы скрывается (canToggle=false).
  const forced = brand.lightOnly

  const [isDark, setIsDark] = useState(() =>
    forced ? false : localStorage.getItem('theme') !== 'light',
  )

  const toggle = () => {
    if (forced) return
    const next = !isDark
    setIsDark(next)
    localStorage.setItem('theme', next ? 'dark' : 'light')
  }

  // FE-08: the effect is the single source that syncs the DOM class to `isDark`
  // (runs on mount and on every change), so the handler no longer toggles it
  // manually — removing the duplicate and the missing-dep warning.
  useEffect(() => {
    document.body.classList.toggle('light', !isDark)
  }, [isDark])

  return { isDark, toggle, canToggle: !forced }
}
