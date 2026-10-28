// Конфиг авто-менеджера (авто-назначение ночных заявок + режим ИИ). Зеркало
// backend-схем uk_management_bot/api/auto_manager/schemas.py:
//   AutoManagerConfigData — тело PUT (только хранимые поля);
//   AutoManagerConfigOut  — ответ GET/PUT (+ read-only состояние площадки).
//
// В отличие от board_config, эндпоинт приватный (manager|admin) — нет
// "публичная страница не должна выглядеть пустой" сценария board_config'а,
// поэтому здесь намеренно НЕТ defaultAutoManagerConfig-фолбэка: карточка
// просто показывает loading/error state, пока/если сервер не ответил.

// "ai" принимается бэкендом только при деплой-флаге площадки
// (AI_MANAGER_ENABLED) — доступность приходит read-only полем `ai_available`.
export type AutoManagerMode = 'rule' | 'ai'

export type AiTemplateKey =
  | 'sla.executor_overdue'
  | 'sla.staff_group'
  | 'sla.manager_overdue'
  | 'sla.reassign_failed'
  | 'sla.reassigned_old'
  | 'sla.clarification_reminder'
  | 'sla.clarification_manager'
  | 'sla.executed_unconfirmed'
  | 'sla.auto_accepted'
  | 'sla.critical_unassigned'
  | 'public.assigned'
  | 'public.executed'

/** Переопределение текста пинга; отсутствующий язык = стандартный текст. */
export interface AiTemplateOverride {
  ru?: string
  uz?: string
}

export interface AutoManagerAiConfig {
  min_confidence: number
  clarify_enabled: boolean
  dedup_enabled: boolean
  /** Правила УК для триажа заявок (≤ 2000 символов, в системный промпт). */
  triage_instructions: string
  /** Правила УК для анализа новостей об отключениях (≤ 2000). */
  news_instructions: string
  /** Дополнительные аварийные слова; базовые (`base_emergency_keywords`) неотключаемы. */
  extra_emergency_keywords: string[]
  /** Только переопределения; стандартные тексты — в `template_defaults` ответа. */
  templates: Partial<Record<AiTemplateKey, AiTemplateOverride>>
}

export type LadderStep = 'remind_executor' | 'staff_group' | 'manager' | 'reassign'

export interface AutoManagerSlaConfig {
  in_progress_max: SlaHours
  clarification_max: number
  executed_unconfirmed_max: number
  completed_unaccepted_days: number
  critical_unassigned_minutes: number
  ladder: Record<LadderStep, number>
  /** Выключенная ступень считается пройденной: пинга нет, следующая — по своему смещению. */
  ladder_enabled: Record<LadderStep, boolean>
  public_status: { enabled: boolean; min_urgency: 'critical' | 'high' }
}

export interface SlaHours {
  critical: number
  high: number
  medium: number
  low: number
}

/** Предохранитель ИИ-триажа (`services/ai_manager/breaker.py`). */
export interface AiBreakerStatus {
  open: boolean
  /** Секунд до автоматического закрытия (0 — закрыт). */
  open_ttl: number
  failures: number
}

export interface AiTemplateDefault {
  ru: string
  uz: string
  placeholders: string[]
}

/** Тело PUT — только хранимые поля конфига. */
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
  ai: AutoManagerAiConfig
  /** SLA-лестница ИИ-менеджера (часы/дни/минуты, 0 = выключено). */
  sla: AutoManagerSlaConfig
}

/** Ответ GET/PUT: конфиг + read-only состояние площадки (в PUT не отправляется). */
export interface AutoManagerConfigOut extends AutoManagerConfigData {
  ai_available: boolean
  /** null — ИИ выключен на площадке или Redis недоступен. */
  ai_status: AiBreakerStatus | null
  template_defaults: Record<AiTemplateKey, AiTemplateDefault>
  base_emergency_keywords: string[]
}

export const AUTO_MANAGER_READ_ONLY_FIELDS = [
  'ai_available', 'ai_status', 'template_defaults', 'base_emergency_keywords',
] as const
