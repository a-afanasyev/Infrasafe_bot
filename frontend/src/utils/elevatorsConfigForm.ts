import { parseIntList, toIntOrNull } from './elevatorsFormat'
import type { ElevatorsConfigIn, ElevatorsConfigOut } from '../types/elevators'

/**
 * Чистая модель формы настроек модуля «Лифты» (черновик инпутов ↔ PUT /config).
 * Пустой порог = «не напоминать» → null; стадии — список дней через запятую.
 */

export interface ElevatorsConfigDraft {
  module_public: boolean
  not_working: string
  under_repair: string
  repair_started: boolean
  maintenance_started: boolean
  back_in_service: boolean
  maintenance: string
  certification: string
  contract: string
  overdue_weekly: boolean
}

const listToStr = (xs: number[]) => xs.join(', ')

export function configDraftFrom(c: ElevatorsConfigOut): ElevatorsConfigDraft {
  return {
    module_public: c.module_public,
    not_working: c.downtime_threshold_days.not_working?.toString() ?? '',
    under_repair: c.downtime_threshold_days.under_repair?.toString() ?? '',
    repair_started: c.resident_notifications.repair_started,
    maintenance_started: c.resident_notifications.maintenance_started,
    back_in_service: c.resident_notifications.back_in_service,
    maintenance: listToStr(c.staff_reminders.maintenance),
    certification: listToStr(c.staff_reminders.certification),
    contract: listToStr(c.staff_reminders.contract),
    overdue_weekly: c.staff_reminders.overdue_weekly,
  }
}

/** Список неотрицательных целых через запятую/точку с запятой/пробел (или пусто). */
export const INT_LIST_RE = /^\s*(\d+\s*([,;\s]\s*\d+\s*)*)?$/

export function isValidStages(value: string): boolean {
  return INT_LIST_RE.test(value)
}

export function configDraftToPayload(d: ElevatorsConfigDraft): ElevatorsConfigIn {
  return {
    module_public: d.module_public,
    downtime_threshold_days: {
      not_working: toIntOrNull(d.not_working),
      under_repair: toIntOrNull(d.under_repair),
    },
    resident_notifications: {
      repair_started: d.repair_started,
      maintenance_started: d.maintenance_started,
      back_in_service: d.back_in_service,
    },
    staff_reminders: {
      maintenance: parseIntList(d.maintenance),
      certification: parseIntList(d.certification),
      contract: parseIntList(d.contract),
      overdue_weekly: d.overdue_weekly,
    },
  }
}
