import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Input } from '@/components/ui/input'
import type { AiProblemsConfig } from '../../types/autoManagerConfig'

// ИИ-разбор «Топ-10 проблем» (страница «Правила ИИ»): кнопка в аналитике,
// разбор в ежемесячном отчёте и ограничения запусков. Диапазоны — как у сервера
// (`_PROBLEMS_RANGES` в services/auto_manager/config.py): вне диапазона значение
// в черновик не попадает, поле подсвечено, а страница блокирует «Сохранить».
interface AiProblemsFormProps {
  value: AiProblemsConfig
  onChange: (problems: AiProblemsConfig) => void
  /** false — в каком-то поле невалидный ввод (страница не даёт сохранить). */
  onValidityChange: (valid: boolean) => void
}

type NumberKey = 'rerun_cooldown_minutes' | 'min_interval_minutes' | 'daily_limit'
type Texts = Record<NumberKey, string>

const RANGES: Record<NumberKey, [number, number]> = {
  rerun_cooldown_minutes: [0, 7 * 24 * 60],
  min_interval_minutes: [1, 24 * 60],
  daily_limit: [1, 30],
}
const NUMBER_KEYS = Object.keys(RANGES) as NumberKey[]

function parseIn(raw: string, [low, high]: [number, number]): number | null {
  if (!/^\d+$/.test(raw.trim())) return null
  const n = Number(raw)
  return n >= low && n <= high ? n : null
}

function textsFrom(value: AiProblemsConfig, keep?: Texts): Texts {
  // Сохранить ввод поля, если он уже соответствует значению (не сбивать курсор/формат).
  return Object.fromEntries(NUMBER_KEYS.map(k => [
    k, keep && parseIn(keep[k], RANGES[k]) === value[k] ? keep[k] : String(value[k]),
  ])) as Texts
}

export default function AiProblemsForm({ value, onChange, onValidityChange }: AiProblemsFormProps) {
  const { t } = useTranslation()
  // Сырой текст полей локально: «» и промежуточный ввод не должны затирать черновик.
  const [texts, setTexts] = useState<Texts>(() => textsFrom(value))
  // Родитель заменил черновик (ответ сервера, опрос) — поля показывают его значения,
  // в т.ч. поверх невалидного ввода: иначе поле и черновик расходились бы молча.
  const [seen, setSeen] = useState(value)
  if (value !== seen) {
    setSeen(value)
    setTexts(textsFrom(value, texts))
  }
  const valid = NUMBER_KEYS.every(k => parseIn(texts[k], RANGES[k]) !== null)
  useEffect(() => { onValidityChange(valid) }, [valid, onValidityChange])

  const field = (key: NumberKey) => {
    const [low, high] = RANGES[key]
    const invalid = parseIn(texts[key], RANGES[key]) === null
    return (
      <label key={key} className="flex flex-col gap-1 text-[11px] text-text-muted">
        {t(`aiManager.problems.${key}`)}
        <Input
          type="number" min={low} max={high} step={1} className="w-28 h-7 text-xs"
          value={texts[key]}
          aria-label={t(`aiManager.problems.${key}`)}
          aria-invalid={invalid}
          onChange={(e) => {
            const next = { ...texts, [key]: e.target.value }
            setTexts(next)
            const n = parseIn(e.target.value, RANGES[key])
            if (n !== null && n !== value[key]) {
              const updated = { ...value, [key]: n }
              setSeen(updated)   // своё изменение — не повод перезаписывать поля
              onChange(updated)
            }
          }}
        />
        <span className={invalid ? 'text-red' : undefined}>
          {t(`aiManager.problems.${key}Hint`, { low, high })}
        </span>
      </label>
    )
  }

  return (
    <div className="flex flex-col gap-3">
      <p className="text-[11px] text-text-muted">{t('aiManager.problems.subtitle')}</p>
      <div className="flex flex-wrap gap-4 text-[13px] text-text-primary">
        <label className="flex items-center gap-2">
          <input type="checkbox" checked={value.manual_enabled}
            onChange={(e) => {
              const updated = { ...value, manual_enabled: e.target.checked }
              setSeen(updated)
              onChange(updated)
            }} />
          {t('aiManager.problems.manual_enabled')}
        </label>
        <label className="flex items-center gap-2">
          <input type="checkbox" checked={value.monthly_enabled}
            onChange={(e) => {
              const updated = { ...value, monthly_enabled: e.target.checked }
              setSeen(updated)
              onChange(updated)
            }} />
          {t('aiManager.problems.monthly_enabled')}
        </label>
      </div>
      <div className="flex flex-wrap gap-5">{NUMBER_KEYS.map(field)}</div>
    </div>
  )
}
