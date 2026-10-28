import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { toast } from 'sonner'
import { useAutoManagerConfig, useUpdateAutoManagerConfig } from '../../hooks/useAutoManagerConfig'
import { safeErrorMessage } from '@/utils/errorMessage'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import LoadingSpinner from '../shared/LoadingSpinner'
import AutoManagerToggle from '../shared/AutoManagerToggle'
import { cn } from '@/lib/utils'
import { useCan } from '../../hooks/useCan'
import type { AutoManagerConfigData, AutoManagerSlaConfig } from '../../types/autoManagerConfig'
import { readStorage, writeStorage } from '../../utils/safeStorage'
import SlaEditor from './AutoManagerSlaEditor'

// Строгий HH:MM (00-23:00-59) — минимальная client-side проверка формы, ДО
// сети. Полную бизнес-валидацию (IANA-таймзона, диапазон max_requests и т.д.)
// делает бэкенд (`validate_config`) — здесь только форма поля, чтобы не
// задвоить источник правды (см. schemas.py комментарий).
const HH_MM_RE = /^([01]\d|2[0-3]):[0-5]\d$/

function isValidHHMM(value: string): boolean {
  return HH_MM_RE.test(value)
}

// Карточка «Автоматический менеджер» на ShiftsPage (домен дежурств). Phase-1
// scope зеркалит бот-UI (handlers/auto_manager.py): редактируемы только
// enabled + окно работы; mode зафиксирован на "rule" — кнопка "ИИ" кликабельна
// и показывает пояснение, но не пишет в конфиг (заглушка до Фазы 2);
// timezone/max_requests_per_run — только просмотр.
const COLLAPSED_KEY = 'uk.shifts.autoManagerCollapsed'

export default function AutoManagerCard() {
  const { t } = useTranslation()
  const { data, isLoading, isError, error } = useAutoManagerConfig()
  const updateConfig = useUpdateAutoManagerConfig()
  const canConfigureRules = useCan('auto_manager.configure')

  // Свёрнут по умолчанию (решение владельца 2026-08-27: карточка съедала
  // много места над расписанием). Выбор запоминается в localStorage.
  const [collapsed, setCollapsed] = useState<boolean>(
    () => readStorage(COLLAPSED_KEY) !== '0',
  )
  const toggleCollapsed = () => {
    setCollapsed(prev => {
      const next = !prev
      writeStorage(COLLAPSED_KEY, next ? '1' : '0')
      return next
    })
  }

  // Черновик окна редактируется отдельно от enabled-тумблера (который шлёт
  // мутацию сразу) — пользователь правит оба поля времени и жмёт "Сохранить".
  const [seededFrom, setSeededFrom] = useState<AutoManagerConfigData | null>(null)
  const [windowStart, setWindowStart] = useState('')
  const [windowEnd, setWindowEnd] = useState('')
  const [windowError, setWindowError] = useState<string | null>(null)

  // 30s-опрос/фокус-рефетч (useAutoManagerConfig) может принести новый `data`
  // по причине, не связанной с окном (напр. бот переключил enabled) — если
  // тогда безусловно ресидить windowStart/End, несохранённая правка окна
  // молча стирается. Ресидим окно только если черновик ещё не разошёлся с
  // последним просиженным значением (пользователь не начал печатать).
  if (data && data !== seededFrom) {
    const windowUntouched =
      seededFrom === null ||
      (windowStart === seededFrom.window_start && windowEnd === seededFrom.window_end)
    setSeededFrom(data)
    if (windowUntouched) {
      setWindowStart(data.window_start)
      setWindowEnd(data.window_end)
      setWindowError(null)
    }
  }

  if (isLoading) return <LoadingSpinner />

  if (isError || !data) {
    return (
      <div className="bg-bg-card border border-border-default rounded-default p-5">
        <div className="font-[var(--font-display)] font-semibold text-sm text-text-primary mb-2">
          {t('autoManager.title')}
        </div>
        <div className="text-[13px] text-red-500">
          {safeErrorMessage(error, t('autoManager.loadFailed'))}
        </div>
      </div>
    )
  }

  const handleSaveWindow = () => {
    if (!isValidHHMM(windowStart) || !isValidHHMM(windowEnd)) {
      setWindowError(t('autoManager.windowInvalid'))
      return
    }
    setWindowError(null)
    updateConfig.mutate({ window_start: windowStart, window_end: windowEnd })
  }

  const windowDirty = windowStart !== data.window_start || windowEnd !== data.window_end

  // Режим пишется только когда площадка его поддерживает (read-only
  // `ai_available` от API = деплой-флаг AI_MANAGER_ENABLED); иначе клик по
  // «ИИ» — только пояснение, без записи (симметрично боту,
  // handlers/auto_manager.py::handle_auto_manager_mode_ai).
  const aiAvailable = data.ai_available === true
  const setMode = (mode: AutoManagerConfigData['mode']) => {
    if (mode === data.mode || updateConfig.isPending) return
    updateConfig.mutate({ mode })
  }
  const handleModeAiClick = () => {
    if (!aiAvailable) {
      toast.info(t('autoManager.modeAiHint'))
      return
    }
    setMode('ai')
  }

  return (
    <div className={cn(
      'bg-bg-card border border-border-default rounded-default flex flex-col',
      collapsed ? 'px-5 py-3' : 'p-5 gap-4',
    )}>
      <div className="flex items-center justify-between gap-3">
        <button
          type="button"
          onClick={toggleCollapsed}
          aria-expanded={!collapsed}
          title={collapsed ? t('autoManager.expand') : t('autoManager.collapse')}
          className="flex items-center gap-2 text-left group"
        >
          <span
            aria-hidden
            className="w-5 h-5 rounded-sm border border-border-default flex items-center justify-center text-[13px] leading-none font-bold text-text-muted group-hover:text-text-primary group-hover:border-border-active transition-colors"
          >
            {collapsed ? '+' : '−'}
          </span>
          <span className="font-[var(--font-display)] font-semibold text-sm text-text-primary">
            {t('autoManager.title')}
          </span>
        </button>
        {/* В свёрнутом виде показываем окно работы одной строкой — главный
            факт, который менеджер проверяет чаще всего. */}
        <div className="flex items-center gap-4 min-w-0">
          {canConfigureRules && (
            <Link to="/dashboard/ai-manager" className="text-[11px] text-accent underline whitespace-nowrap">
              {t('aiManager.openPage')}
            </Link>
          )}
          {collapsed && (
            <span className="text-[11px] text-text-muted whitespace-nowrap truncate">
              {t('autoManager.window')}: <span className="text-text-primary font-[var(--font-mono)]">{data.window_start}–{data.window_end}</span>
            </span>
          )}
          <AutoManagerToggle />
        </div>
      </div>

      {collapsed ? null : (<>
      {/* Режим: две кнопки-«вкладки», активная подсвечена. «ИИ» без
          ai_available — только пояснение по клику (ничего не пишет). */}
      <div className="flex flex-col gap-1.5">
        <span className="text-[11px] text-text-muted">{t('autoManager.mode')}</span>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => setMode('rule')}
            aria-pressed={data.mode === 'rule'}
            className={cn(
              'px-3 py-1.5 rounded-sm text-xs font-semibold border transition-colors',
              data.mode === 'rule'
                ? 'bg-accent-dim text-accent border-border-active cursor-default'
                : 'bg-bg-surface text-text-muted border-border-default hover:border-border-active hover:text-text-primary cursor-pointer',
            )}
          >
            {t('autoManager.modeRule')}
          </button>
          <button
            type="button"
            onClick={handleModeAiClick}
            title={aiAvailable ? t('autoManager.modeAiTitle') : t('autoManager.modeAiHint')}
            aria-pressed={data.mode === 'ai'}
            className={cn(
              'px-3 py-1.5 rounded-sm text-xs font-semibold border transition-colors',
              data.mode === 'ai'
                ? 'bg-accent-dim text-accent border-border-active cursor-default'
                : 'bg-bg-surface text-text-muted border-border-default hover:border-border-active hover:text-text-primary cursor-pointer',
              !aiAvailable && 'opacity-60',
            )}
          >
            {t('autoManager.modeAi')}
          </button>
        </div>
      </div>

      {/* Окно работы — редактируемо, сохраняется отдельной кнопкой. */}
      <div className="flex flex-col gap-1.5">
        <span className="text-[11px] text-text-muted">{t('autoManager.window')}</span>
        <div className="flex items-center gap-2 flex-wrap">
          <Input
            type="time"
            className="w-28"
            value={windowStart}
            onChange={(e) => { setWindowStart(e.target.value); setWindowError(null) }}
            aria-label={t('autoManager.windowFrom')}
          />
          <span className="text-text-muted">–</span>
          <Input
            type="time"
            className="w-28"
            value={windowEnd}
            onChange={(e) => { setWindowEnd(e.target.value); setWindowError(null) }}
            aria-label={t('autoManager.windowTo')}
          />
          <Button
            variant="outline"
            size="sm"
            disabled={!windowDirty || updateConfig.isPending}
            onClick={handleSaveWindow}
          >
            {t('autoManager.saveWindow')}
          </Button>
        </div>
        {windowError && <div className="text-[11px] text-red-500">{windowError}</div>}
      </div>

      {/* Read-only Phase-1: timezone/лимит заявок не редактируются на дашборде. */}
      <div className="flex gap-6 text-[11px] text-text-muted">
        <span>{t('autoManager.timezone')}: <span className="text-text-primary">{data.timezone}</span></span>
        <span>{t('autoManager.maxRequests')}: <span className="text-text-primary">{data.max_requests_per_run}</span></span>
      </div>

      {/* SLA-лестница — только там, где ИИ-режим доступен (без него тик не
          зарегистрирован и значения ни на что не влияют). */}
      {aiAvailable && data.sla && (
        <SlaEditor
          value={data.sla}
          pending={updateConfig.isPending}
          onSave={(sla: AutoManagerSlaConfig) => updateConfig.mutate({ sla })}
        />
      )}
      </>)}
    </div>
  )
}
