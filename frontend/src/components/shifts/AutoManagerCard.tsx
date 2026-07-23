import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { useAutoManagerConfig, useUpdateAutoManagerConfig } from '../../hooks/useAutoManagerConfig'
import { safeErrorMessage } from '@/utils/errorMessage'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import LoadingSpinner from '../shared/LoadingSpinner'
import type { AutoManagerConfigData } from '../../types/autoManagerConfig'

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
export default function AutoManagerCard() {
  const { t } = useTranslation()
  const { data, isLoading, isError, error } = useAutoManagerConfig()
  const updateConfig = useUpdateAutoManagerConfig()

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

  const handleToggleEnabled = () => {
    // Патч, не полный объект из (возможно устаревшего) `data` — мутация сама
    // перезапрашивает актуальное состояние перед записью (см.
    // useAutoManagerConfig.ts) и мёржит патч поверх него, а не поверх кеша
    // этого рендера — иначе устаревший `data.enabled` в самом патче не был бы
    // проблемой (мы шлём только `enabled`), но полный объект из старого
    // рендера мог бы затереть ДРУГИЕ поля, изменённые ботом тем временем.
    updateConfig.mutate({ enabled: !data.enabled })
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

  // Клик по ИИ-режиму НИКОГДА не пишет в конфиг — только показывает пояснение
  // (симметрично боту, handlers/auto_manager.py::handle_auto_manager_mode_ai,
  // который на этот же callback отвечает `callback.answer(hint)` без записи).
  // Phase-1: mode зафиксирован на "rule", ИИ ждёт ANTHROPIC_API_KEY (Фаза 2).
  const handleModeAiClick = () => {
    toast.info(t('autoManager.modeAiHint'))
  }

  return (
    <div className="bg-bg-card border border-border-default rounded-default p-5 flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <span className="font-[var(--font-display)] font-semibold text-sm text-text-primary">
          {t('autoManager.title')}
        </span>
        <label className="flex items-center gap-2 text-xs text-text-muted cursor-pointer">
          <span className={data.enabled ? 'text-emerald font-semibold' : 'text-text-muted'}>
            {data.enabled ? t('autoManager.enabledOn') : t('autoManager.enabledOff')}
          </span>
          <input
            type="checkbox"
            checked={data.enabled}
            onChange={handleToggleEnabled}
            disabled={updateConfig.isPending}
            aria-label={t('autoManager.toggleLabel')}
          />
        </label>
      </div>

      {/* Режим — symmetric с ботом: "по правилу" зафиксирован (единственный
          рабочий в Phase 1), "ИИ" КЛИКАБЕЛЕН — но клик только показывает
          пояснение (toast), НИКОГДА не пишет mode="ai" в конфиг. Раньше кнопка
          была HTML-disabled ("мёртвая"); по запросу пользователя заменено на
          явный интерактивный клик с тултипом — так понятнее, что опция
          существует и когда-нибудь заработает, а не просто сломана. */}
      <div className="flex flex-col gap-1.5">
        <span className="text-[11px] text-text-muted">{t('autoManager.mode')}</span>
        <div className="flex gap-2">
          <button
            type="button"
            disabled
            aria-pressed="true"
            className="px-3 py-1.5 rounded-sm text-xs font-semibold bg-accent-dim text-accent border border-border-active cursor-default"
          >
            {t('autoManager.modeRule')}
          </button>
          <button
            type="button"
            onClick={handleModeAiClick}
            title={t('autoManager.modeAiHint')}
            aria-pressed="false"
            className="px-3 py-1.5 rounded-sm text-xs font-semibold bg-bg-surface text-text-muted border border-border-default hover:border-border-active hover:text-text-primary transition-colors cursor-pointer"
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
    </div>
  )
}
