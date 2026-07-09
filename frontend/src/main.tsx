import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BRAND, brand } from './brand/brand'
import './i18n'
import './index.css'
import App from './App'

// Применяем бренд синхронно до рендера — иначе тёмная вспышка (FOUC) на светлом
// PROFK. data-brand активирует CSS-блок токенов; light-only бренд сразу светлый.
document.documentElement.dataset.brand = BRAND
if (brand.lightOnly) document.body.classList.add('light')

// Авто-восстановление после деплоя фронта: lazy-страницы грузятся отдельными
// чанками с хэшем в имени; новый билд удаляет старые файлы. Если открытая сессия
// (client-side routing) переходит на страницу, чей старый чанк уже 404, Vite шлёт
// `vite:preloadError`, а dynamic import падает → PageErrorBoundary показывает
// ошибку, и «Повторить» бесполезно (чанк всё ещё 404). Здесь один раз
// перезагружаем страницу, чтобы подтянуть свежий index.html и актуальные чанки.
// sessionStorage-guard (окно 10с) защищает от цикла при реальной сетевой ошибке.
window.addEventListener('vite:preloadError', () => {
  const KEY = 'chunk-reload-at'
  const last = Number(sessionStorage.getItem(KEY) || 0)
  if (Date.now() - last > 10_000) {
    sessionStorage.setItem(KEY, String(Date.now()))
    window.location.reload()
  }
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
