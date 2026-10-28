import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import type { AiTemplateDefault, AiTemplateKey, AiTemplateOverride } from '../../types/autoManagerConfig'

// Тексты уведомлений ИИ-менеджера: на каждый ключ — RU и UZ. Хранятся только
// переопределения; пустое поле = стандартный текст (он же — placeholder).
// Свёрнуто через нативный <details>: без состояния.
interface AiTemplatesEditorProps {
  value: Partial<Record<AiTemplateKey, AiTemplateOverride>>
  defaults: Record<AiTemplateKey, AiTemplateDefault>
  onChange: (templates: Partial<Record<AiTemplateKey, AiTemplateOverride>>) => void
}

const LANGS = ['ru', 'uz'] as const
const FIELD = 'w-full rounded-sm border border-border-default bg-bg-surface p-2 text-[12px] text-text-primary'

export default function AiTemplatesEditor({ value, defaults, onChange }: AiTemplatesEditorProps) {
  const { t } = useTranslation()
  const keys = Object.keys(defaults) as AiTemplateKey[]

  const set = (key: AiTemplateKey, lang: 'ru' | 'uz', text: string) => {
    const next = { ...(value[key] ?? {}), [lang]: text }
    onChange({ ...value, [key]: next })
  }
  const reset = (key: AiTemplateKey) =>
    onChange(Object.fromEntries(Object.entries(value).filter(([k]) => k !== key)))

  return (
    <details className="flex flex-col gap-3">
      <summary className="cursor-pointer text-[13px] font-semibold text-text-primary">{t('aiManager.templates.title')}</summary>
      <div className="mt-3 flex flex-col gap-4">
        {keys.map((key) => (
          <div key={key} className="flex flex-col gap-1 border-t border-border-default pt-2">
            <div className="flex items-center justify-between gap-2">
              <span className="text-[12px] font-semibold text-text-primary">{t(`aiManager.templates.keys.${key}`)}</span>
              {value[key] && (
                <Button variant="outline" size="sm" onClick={() => reset(key)}>{t('aiManager.templates.reset')}</Button>
              )}
            </div>
            <span className="text-[10px] text-text-muted">
              {t('aiManager.templates.hint', { placeholders: defaults[key].placeholders.map((p) => `{${p}}`).join(', ') })}
            </span>
            {LANGS.map((lang) => (
              <label key={lang} className="flex items-start gap-2 text-[11px] text-text-muted">
                <span className="w-6 pt-2">{t(`aiManager.templates.${lang}`)}</span>
                <textarea
                  className={FIELD} rows={2}
                  value={value[key]?.[lang] ?? ''}
                  placeholder={defaults[key][lang]}
                  aria-label={`${t(`aiManager.templates.keys.${key}`)} ${t(`aiManager.templates.${lang}`)}`}
                  onChange={(e) => set(key, lang, e.target.value)}
                />
              </label>
            ))}
          </div>
        ))}
      </div>
    </details>
  )
}
