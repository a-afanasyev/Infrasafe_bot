/**
 * Фича-флаги фронта (build-time `VITE_*`). Читаются функцией, а не константой
 * модуля, чтобы тесты могли переключать флаг через `vi.stubEnv` без сброса
 * кеша модулей.
 */

/** Модуль «Лифты» (согласованно с backend ELEVATORS_ENABLED). */
export function isElevatorsEnabled(): boolean {
  return import.meta.env.VITE_ELEVATORS_ENABLED === 'true'
}
