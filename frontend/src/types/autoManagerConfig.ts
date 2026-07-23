// Конфиг авто-менеджера (авто-назначение ночных заявок). Зеркало backend-схемы
// uk_management_bot/api/auto_manager/schemas.py::AutoManagerConfigData.
//
// В отличие от board_config, этот эндпоинт приватный (manager|admin) — нет
// "публичная страница не должна выглядеть пустой" сценария board_config'а,
// поэтому здесь намеренно НЕТ defaultAutoManagerConfig-фолбэка: карточка
// просто показывает loading/error state, пока/если сервер не ответил.

// Backend API-схема (schemas.py) намеренно ýже общего валидатора бота
// (services/auto_manager/config.py::validate_config, который принимает и
// "ai" — forward-compat под Phase 2): пока оркестратор не читает `mode`
// вообще и ни бот, ни дашборд не могут выбрать "ai", API отдаёт/принимает
// только "rule". Расширить до 'rule' | 'ai' — когда Phase 2 подключит
// ИИ-движок к оркестратору, не раньше.
export type AutoManagerMode = 'rule'

export interface AutoManagerConfigData {
  enabled: boolean
  mode: AutoManagerMode
  window_start: string // HH:MM
  window_end: string // HH:MM
  timezone: string // IANA, напр. "Asia/Tashkent"
  max_requests_per_run: number
}
