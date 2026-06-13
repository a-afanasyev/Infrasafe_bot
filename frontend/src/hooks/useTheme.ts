import { useState, useEffect } from 'react'

export function useTheme() {
  const [isDark, setIsDark] = useState(() => {
    return localStorage.getItem('theme') !== 'light'
  })

  const toggle = () => {
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

  return { isDark, toggle }
}
