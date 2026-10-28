import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { usePageTitle } from '../hooks/usePageTitle'
import { useAutoManagerConfig, useResetAiBreaker, useUpdateAutoManagerConfig } from '../hooks/useAutoManagerConfig'
import LoadingSpinner from '../components/shared/LoadingSpinner'
import AiBreakerBanner from '../components/aiManager/AiBreakerBanner'
import AiTemplatesEditor from '../components/aiManager/AiTemplatesEditor'
import AiTriageForm from '../components/aiManager/AiTriageForm'
import SlaEditor from '../components/shifts/AutoManagerSlaEditor'
import type { AutoManagerConfigOut } from '../types/autoManagerConfig'

/**
 * «Правила ИИ-менеджера» (/dashboard/ai-manager, auto_manager.configure):
 * режим, триаж заявок, SLA-лестница, тексты уведомлений — один черновик,
 * одна кнопка «Сохранить правила» (PUT полного конфига поверх свежего GET,
 * см. useUpdateAutoManagerConfig). Сброс предохранителя — отдельный POST.
 */
type Draft = Pick<AutoManagerConfigOut, 'enabled' | 'mode' | 'ai' | 'sla'>
type ModeChoice = 'off' | 'rule' | 'ai'

function toDraft(data: AutoManagerConfigOut): Draft {
  return { enabled: data.enabled, mode: data.mode, ai: data.ai, sla: data.sla }
}

function modeOf(draft: Draft): ModeChoice {
  return draft.enabled ? draft.mode : 'off'
}

const MODES: ModeChoice[] = ['off', 'rule', 'ai']

export default function AiManagerPage() {
  const { t } = useTranslation()
  usePageTitle(t('aiManager.title'))
  const { data, isLoading, isError } = useAutoManagerConfig()
  const updateConfig = useUpdateAutoManagerConfig()
  const resetBreaker = useResetAiBreaker()

  // Черновик сидится из свежих данных, пока пользователь его не правил
  // (тот же приём, что в AutoManagerSlaEditor): 30-секундный опрос не стирает ввод.
  const [seededFrom, setSeededFrom] = useState<AutoManagerConfigOut | null>(null)
  const [draft, setDraft] = useState<Draft | null>(null)
  if (data && data !== seededFrom) {
    const untouched = seededFrom === null || draft === null
      || JSON.stringify(draft) === JSON.stringify(toDraft(seededFrom))
    setSeededFrom(data)
    if (untouched) setDraft(toDraft(data))
  }

  if (isLoading || (!data && !isError)) return <LoadingSpinner />
  if (isError || !data || !draft) {
    return <div className="text-[13px] text-red-500">{t('autoManager.loadFailed')}</div>
  }

  const dirty = JSON.stringify(draft) !== JSON.stringify(toDraft(data))
  const setMode = (choice: ModeChoice) =>
    setDraft(choice === 'off' ? { ...draft, enabled: false } : { ...draft, enabled: true, mode: choice })

  return (
    <div className="flex flex-col gap-5 max-w-4xl">
      <div>
        <h1 className="font-[var(--font-display)] font-semibold text-lg text-text-primary">{t('aiManager.title')}</h1>
        <p className="text-[12px] text-text-muted">{t('aiManager.subtitle')}</p>
      </div>

      {!data.ai_available && (
        <div className="rounded-default border border-border-default bg-bg-surface p-3 text-[12px] text-text-muted">
          {t('aiManager.unavailable')}
        </div>
      )}

      <section className="bg-bg-card border border-border-default rounded-default p-5 flex flex-col gap-3">
        <span className="text-[11px] text-text-muted">{t('aiManager.mode.title')}</span>
        <div className="flex gap-2">
          {MODES.map((choice) => (
            <button
              key={choice}
              type="button"
              onClick={() => setMode(choice)}
              disabled={choice === 'ai' && !data.ai_available}
              aria-pressed={modeOf(draft) === choice}
              title={choice === 'ai' && !data.ai_available ? t('autoManager.modeAiHint') : undefined}
              className={cn(
                'px-3 py-1.5 rounded-sm text-xs font-semibold border transition-colors',
                modeOf(draft) === choice
                  ? 'bg-accent-dim text-accent border-border-active cursor-default'
                  : 'bg-bg-surface text-text-muted border-border-default hover:border-border-active hover:text-text-primary cursor-pointer',
                choice === 'ai' && !data.ai_available && 'opacity-60 cursor-not-allowed',
              )}
            >
              {t(`aiManager.mode.${choice}`)}
            </button>
          ))}
        </div>
        {data.ai_available && (
          <AiBreakerBanner status={data.ai_status} pending={resetBreaker.isPending} onReset={() => resetBreaker.mutate()} />
        )}
      </section>

      <section className="bg-bg-card border border-border-default rounded-default p-5 flex flex-col gap-3">
        <span className="text-[13px] font-semibold text-text-primary">{t('aiManager.triage.title')}</span>
        <AiTriageForm value={draft.ai} baseKeywords={data.base_emergency_keywords}
          onChange={(ai) => setDraft({ ...draft, ai })} />
      </section>

      <section className="bg-bg-card border border-border-default rounded-default p-5">
        <SlaEditor value={draft.sla} onChange={(sla) => setDraft({ ...draft, sla })} />
      </section>

      <section className="bg-bg-card border border-border-default rounded-default p-5">
        <AiTemplatesEditor value={draft.ai.templates} defaults={data.template_defaults}
          onChange={(templates) => setDraft({ ...draft, ai: { ...draft.ai, templates } })} />
      </section>

      <div>
        <Button disabled={!dirty || updateConfig.isPending} onClick={() => updateConfig.mutate(draft)}>
          {t('aiManager.save')}
        </Button>
      </div>
    </div>
  )
}
