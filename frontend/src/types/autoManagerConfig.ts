// Конфиг авто-менеджера (авто-назначение ночных заявок). Зеркало backend-схемы
// uk_management_bot/api/auto_manager/schemas.py::AutoManagerConfigData.
//
// В отличие от board_config, этот эндпоинт приватный (manager|admin) — нет
// "публичная страница не должна выглядеть пустой" сценария board_config'а,
// поэтому здесь намеренно НЕТ defaultAutoManagerConfig-фолбэка: карточка
// просто показывает loading/error state, пока/если сервер не ответил.

// "ai" принимается бэкендом только при деплой-флаге площадки
// (AI_MANAGER_ENABLED) — доступность приходит read-only полем `ai_available`.
export type AutoManagerMode = 'rule' | 'ai'

export interface AutoManagerAiConfig {
  min_confidence: number
  clarify_enabled: boolean
  dedup_enabled: boolean
}

export interface AutoManagerConfigData {
  enabled: boolean
  mode: AutoManagerMode
  window_start: string // HH:MM
  window_end: string // HH:MM
  timezone: string // IANA, напр. "Asia/Tashkent"
  max_requests_per_run: number
  /** Нормативы сроков аналитики, часы от создания до сдачи работы. */
  sla_hours: SlaHours
  /** Блок ИИ-режима; бэкенд подставляет дефолт, если поля нет. */
  ai?: AutoManagerAiConfig
  /** Read-only: доступен ли режим "ai" на этой площадке. */
  ai_available?: boolean
}

export interface SlaHours {
  critical: number
  high: number
  medium: number
  low: number
}
