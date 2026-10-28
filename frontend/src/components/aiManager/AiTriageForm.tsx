import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Input } from '@/components/ui/input'
import type { AutoManagerAiConfig } from '../../types/autoManagerConfig'

// Триаж заявок (страница «Правила ИИ»): порог уверенности, уточнение, дубли,
// дополнительные аварийные слова, инструкции для триажа и для новостей.
// Источник истины — черновик страницы; локально только сырой текст ключевых слов.
interface AiTriageFormProps {
  value: AutoManagerAiConfig
  /** Базовые аварийные слова из ответа API — неотключаемы, только показ. */
  baseKeywords: string[]
  onChange: (ai: AutoManagerAiConfig) => void
}

const INSTRUCTIONS_MAX = 2000
const FIELD = 'w-full rounded-sm border border-border-default bg-bg-surface p-2 text-[13px] text-text-primary'

function keywordsToText(words: string[]): string {
  return words.join(', ')
}

function textToKeywords(text: string): string[] {
  return text.split(/[,\n]/).map((w) => w.trim()).filter(Boolean)
}

export default function AiTriageForm({ value, baseKeywords, onChange }: AiTriageFormProps) {
  const { t } = useTranslation()
  // Сырой текст ключевых слов — локально: иначе контролируемое поле терял бы
  // запятую/пробел при каждом нажатии (массив ↔ строка нормализуется).
  const [keywordsText, setKeywordsText] = useState(keywordsToText(value.extra_emergency_keywords))
  const instructions = (key: 'triage_instructions' | 'news_instructions', label: string, hint: string) => (
    <label className="flex flex-col gap-1 text-[11px] text-text-muted">
      {label}
      <textarea
        className={FIELD}
        rows={5}
        maxLength={INSTRUCTIONS_MAX}
        value={value[key]}
        placeholder={hint}
        aria-label={label}
        onChange={(e) => onChange({ ...value, [key]: e.target.value })}
      />
      <span className="self-end">{t('aiManager.triage.count', { n: value[key].length })}</span>
    </label>
  )

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-4 text-[13px] text-text-primary">
        <label className="flex items-center gap-2 text-[11px] text-text-muted">
          {t('aiManager.triage.minConfidence')}
          <Input
            type="number" min={0} max={1} step={0.05} className="w-20 h-7 text-xs"
            value={value.min_confidence}
            aria-label={t('aiManager.triage.minConfidence')}
            onChange={(e) => onChange({ ...value, min_confidence: Number.parseFloat(e.target.value) || 0 })}
          />
        </label>
        <label className="flex items-center gap-2">
          <input type="checkbox" checked={value.clarify_enabled}
            onChange={(e) => onChange({ ...value, clarify_enabled: e.target.checked })} />
          {t('aiManager.triage.clarify')}
        </label>
        <label className="flex items-center gap-2">
          <input type="checkbox" checked={value.dedup_enabled}
            onChange={(e) => onChange({ ...value, dedup_enabled: e.target.checked })} />
          {t('aiManager.triage.dedup')}
        </label>
      </div>
      <p className="text-[11px] text-text-muted">
        {t('aiManager.triage.keywordsBase', { list: keywordsToText(baseKeywords) })}
      </p>
      <label className="flex flex-col gap-1 text-[11px] text-text-muted">
        {t('aiManager.triage.keywordsExtra')}
        <textarea
          className={FIELD} rows={2}
          value={keywordsText}
          aria-label={t('aiManager.triage.keywordsExtra')}
          onChange={(e) => {
            setKeywordsText(e.target.value)
            onChange({ ...value, extra_emergency_keywords: textToKeywords(e.target.value) })
          }}
        />
      </label>
      {instructions('triage_instructions', t('aiManager.triage.triageInstructions'), t('aiManager.triage.triageInstructionsHint'))}
      {instructions('news_instructions', t('aiManager.triage.newsInstructions'), t('aiManager.triage.newsInstructionsHint'))}
    </div>
  )
}
