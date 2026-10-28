/**
 * Фича-флаги фронта (build-time `VITE_*`). Читаются функцией, а не константой
 * модуля, чтобы тесты могли переключать флаг через `vi.stubEnv` без сброса
 * кеша модулей.
 */

/** Модуль «Лифты» (согласованно с backend ELEVATORS_ENABLED). */
export function isElevatorsEnabled(): boolean {
  return import.meta.env.VITE_ELEVATORS_ENABLED === 'true'
}

/** Витрина «до/после» (согласованно с backend WORK_REPORTS_ENABLED). */
export function isWorkReportsEnabled(): boolean {
  return import.meta.env.VITE_WORK_REPORTS_ENABLED === 'true'
}

/** Мониторинг отключений (согласованно с backend NEWS_WATCH_ENABLED). */
export function isNewsWatchEnabled(): boolean {
  return import.meta.env.VITE_NEWS_WATCH_ENABLED === 'true'
}
