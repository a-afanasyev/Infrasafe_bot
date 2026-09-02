export const AVATAR_GRADIENTS = [
  'linear-gradient(135deg, #3b82f6, #2563eb)',
  'linear-gradient(135deg, #8b5cf6, #7c3aed)',
  'linear-gradient(135deg, #10b981, #059669)',
  'linear-gradient(135deg, #f59e0b, #d97706)',
  'linear-gradient(135deg, #00d4aa, #0099aa)', // brand-allow (categorical avatar palette)
]

// Оформление специализаций. Полноту относительно канона держит
// `employeeUtils.canon.test.ts`: раньше фильтр на странице «Сотрудники»
// строился из ключей этой карты, и новая специализация в него просто не
// попадала — сотрудника с ней нельзя было отфильтровать.
export const SPEC_COLORS: Record<string, string> = {
  'electrician': 'var(--amber)',
  'plumber': 'var(--blue)',
  'heating': 'var(--red)',
  'ventilation': 'var(--teal)',
  'elevator': 'var(--cyan)',
  'cleaning': 'var(--emerald)',
  'security': 'var(--violet)',
  'landscaping': 'var(--green)',
  'repair': 'var(--orange)',
}

export const SPEC_EMOJI: Record<string, string> = {
  'electrician': '⚡',
  'plumber': '🔧',
  'heating': '🔥',
  'ventilation': '💨',
  'elevator': '🛗',
  'cleaning': '🧹',
  'security': '🔒',
  'landscaping': '🌳',
  'repair': '🔨',
}

import type { TFunction } from 'i18next'
import { tSpecialization } from '../i18n/apiMaps'

export function getSpecDisplay(key: string, t: TFunction): string {
  const emoji = SPEC_EMOJI[key] ?? ''
  const label = tSpecialization(key, t)
  return emoji ? `${emoji} ${label}` : label
}

export function getInitials(firstName: string | null, lastName: string | null): string {
  const f = firstName ? firstName[0] : ''
  const l = lastName ? lastName[0] : ''
  return (f + l).toUpperCase() || '?'
}
