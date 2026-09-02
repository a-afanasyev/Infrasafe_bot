import { create } from 'zustand'

import { NAME_CASE_DEFAULT, isNameCase, type NameCase } from '../utils/nameCase'

// Предпочтение менеджера «ФИО заглавными буквами». Живёт в localStorage
// устройства (как тема), без бэка; ключ не по userId — одна машина = один
// менеджер. zustand вместо hook-per-instance (useTheme): все таблицы
// ре-рендерятся при переключении из сайдбара, `getState()` доступен вне React.
export const NAME_CASE_STORAGE_KEY = 'uk.nameCase'

interface NameCaseState {
  mode: NameCase
  setMode: (mode: NameCase) => void
  toggle: () => void
}

export function readStoredNameCase(): NameCase {
  try {
    const stored = localStorage.getItem(NAME_CASE_STORAGE_KEY)
    return isNameCase(stored) ? stored : NAME_CASE_DEFAULT
  } catch {
    return NAME_CASE_DEFAULT
  }
}

function writeStoredNameCase(mode: NameCase): void {
  try {
    localStorage.setItem(NAME_CASE_STORAGE_KEY, mode)
  } catch {
    // приватный режим / квота — предпочтение живёт до перезагрузки
  }
}

export const useNameCaseStore = create<NameCaseState>()((set, get) => ({
  mode: readStoredNameCase(),
  setMode: (mode) => {
    set({ mode })
    writeStoredNameCase(mode)
  },
  toggle: () => get().setMode(get().mode === 'caps' ? 'title' : 'caps'),
}))
