/**
 * Канон специализаций — зеркало `uk_management_bot/constants/specializations.py`.
 *
 * Три формы (приглашение сотрудника, создание смены, шаблон смены) держали
 * один и тот же литеральный список каждая у себя, и он расходился с бэкендом:
 * форма предлагала `elevator`, а диспетчер вычислял `maintenance`. Совпадения
 * не было никогда.
 *
 * Порядок значим — в нём позиции показываются в формах.
 * Расхождение с бэкендом ловит ратчет `test_specialization_canon.py`.
 */
export const SPECIALIZATIONS = [
  'electrician',
  'plumber',
  'heating',
  'ventilation',
  'elevator',
  'cleaning',
  'security',
  'landscaping',
  'repair',
] as const

export type Specialization = (typeof SPECIALIZATIONS)[number]
