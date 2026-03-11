import { useState, useEffect } from 'react'

export function useTheme() {
  const [isDark, setIsDark] = useState(() => {
    return localStorage.getItem('theme') !== 'light'
  })

  const toggle = () => {
    const next = !isDark
    setIsDark(next)
    document.body.classList.toggle('light', !next)
    localStorage.setItem('theme', next ? 'dark' : 'light')
  }

  useEffect(() => {
    document.body.classList.toggle('light', !isDark)
  }, [])

  return { isDark, toggle }
}
