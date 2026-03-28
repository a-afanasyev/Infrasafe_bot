export const AVATAR_GRADIENTS = [
  'linear-gradient(135deg, #3b82f6, #2563eb)',
  'linear-gradient(135deg, #8b5cf6, #7c3aed)',
  'linear-gradient(135deg, #10b981, #059669)',
  'linear-gradient(135deg, #f59e0b, #d97706)',
  'linear-gradient(135deg, #00d4aa, #0099aa)',
]

export const SPEC_COLORS: Record<string, string> = {
  'electrician': 'var(--amber)',
  'plumber': 'var(--blue)',
  'heating': 'var(--red)',
  'cleaning': 'var(--emerald)',
  'security': 'var(--violet)',
  'elevator': 'var(--cyan)',
  'landscaping': 'var(--green)',
  'ventilation': 'var(--teal)',
}

const SPEC_EMOJI: Record<string, string> = {
  'electrician': '⚡',
  'plumber': '🔧',
  'heating': '🔥',
  'cleaning': '🧹',
  'security': '🔒',
  'elevator': '🛗',
  'landscaping': '🌳',
  'ventilation': '💨',
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
