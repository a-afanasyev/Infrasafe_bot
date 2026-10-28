import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import type { NewsWatchConfig } from '../../types/newsWatch'

// Настройки мониторинга: источники (по одному на строку: «@chat Название»),
// описание комплекса для LLM (свободный текст = «страница настроек» вместо
// хардкода адресов), ключевые слова префильтра, auto_publish, каналы рассылки.
// Черновик сидится из конфига один раз; бизнес-валидация — на бэкенде.
interface Props {
  value: NewsWatchConfig
  pending: boolean
  onSave: (cfg: NewsWatchConfig) => void
}

function sourcesToText(sources: NewsWatchConfig['sources']): string {
  return sources.map((s) => (s.title ? `${s.chat} ${s.title}` : s.chat)).join('\n')
}

function textToSources(text: string): NewsWatchConfig['sources'] {
  return text
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const [chat, ...rest] = line.split(/\s+/)
      return { chat, title: rest.join(' ') }
    })
}

export default function NewsWatchConfigForm({ value, pending, onSave }: Props) {
  const { t } = useTranslation()
  const [sources, setSources] = useState(sourcesToText(value.sources))
  const [context, setContext] = useState(value.complex_context)
  const [keywords, setKeywords] = useState(value.keywords.join(', '))
  const [autoPublish, setAutoPublish] = useState(value.auto_publish)
  const [minConfidence, setMinConfidence] = useState(String(value.min_confidence))
  const [broadcast, setBroadcast] = useState(value.broadcast)

  const submit = () => {
    onSave({
      sources: textToSources(sources),
      complex_context: context.trim(),
      keywords: keywords.split(/[,\n]/).map((k) => k.trim()).filter(Boolean),
      auto_publish: autoPublish,
      min_confidence: Number.parseFloat(minConfidence) || 0,
      broadcast,
    })
  }

  const field = 'w-full rounded-sm border border-border-default bg-bg-surface p-2 text-[13px] text-text-primary'

  return (
    <div className="flex flex-col gap-3">
      <label className="flex flex-col gap-1 text-[11px] text-text-muted">
        {t('newsWatch.config.sources')}
        <textarea className={field} rows={4} value={sources} onChange={(e) => setSources(e.target.value)}
          aria-label={t('newsWatch.config.sources')} placeholder="@toshkent_elektr Электросети" />
      </label>
      <label className="flex flex-col gap-1 text-[11px] text-text-muted">
        {t('newsWatch.config.context')}
        <textarea className={field} rows={4} value={context} onChange={(e) => setContext(e.target.value)}
          aria-label={t('newsWatch.config.context')} placeholder={t('newsWatch.config.contextHint')} />
      </label>
      <label className="flex flex-col gap-1 text-[11px] text-text-muted">
        {t('newsWatch.config.keywords')}
        <textarea className={field} rows={2} value={keywords} onChange={(e) => setKeywords(e.target.value)}
          aria-label={t('newsWatch.config.keywords')} />
      </label>
      <div className="flex flex-wrap items-center gap-4 text-[13px] text-text-primary">
        <label className="flex items-center gap-2">
          <input type="checkbox" checked={autoPublish} onChange={(e) => setAutoPublish(e.target.checked)} />
          {t('newsWatch.config.autoPublish')}
        </label>
        <label className="flex items-center gap-2 text-[11px] text-text-muted">
          {t('newsWatch.config.minConfidence')}
          <Input type="number" min={0} max={1} step={0.05} className="w-20 h-7 text-xs" value={minConfidence}
            onChange={(e) => setMinConfidence(e.target.value)} aria-label={t('newsWatch.config.minConfidence')} />
        </label>
        <label className="flex items-center gap-2">
          <input type="checkbox" checked={broadcast.dm}
            onChange={(e) => setBroadcast({ ...broadcast, dm: e.target.checked })} />
          {t('newsWatch.config.broadcastDm')}
        </label>
        <label className="flex items-center gap-2">
          <input type="checkbox" checked={broadcast.residents_groups}
            onChange={(e) => setBroadcast({ ...broadcast, residents_groups: e.target.checked })} />
          {t('newsWatch.config.broadcastGroups')}
        </label>
      </div>
      <div>
        <Button variant="outline" size="sm" disabled={pending} onClick={submit}>
          {t('newsWatch.config.save')}
        </Button>
      </div>
    </div>
  )
}
