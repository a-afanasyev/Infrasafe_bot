export const AVATAR_GRADIENTS = [
  'linear-gradient(135deg, #3b82f6, #2563eb)',
  'linear-gradient(135deg, #8b5cf6, #7c3aed)',
  'linear-gradient(135deg, #10b981, #059669)',
  'linear-gradient(135deg, #f59e0b, #d97706)',
  'linear-gradient(135deg, #00d4aa, #0099aa)',
]

export const SPEC_COLORS: Record<string, string> = {
  'Электрика': 'var(--amber)',
  'Сантехника': 'var(--blue)',
  'Отопление': 'var(--red)',
  'Уборка': 'var(--emerald)',
  'Безопасность': 'var(--violet)',
  'Лифт': 'var(--cyan)',
  'Благоустройство': 'var(--green)',
  'Вентиляция': 'var(--teal)',
}

export function getInitials(firstName: string | null, lastName: string | null): string {
  const f = firstName ? firstName[0] : ''
  const l = lastName ? lastName[0] : ''
  return (f + l).toUpperCase() || '?'
}
