import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { FileSpreadsheet } from 'lucide-react'
import { toast } from 'sonner'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select } from '@/components/ui/select'
import { exportOfficialReport, type OfficialReportOptions } from '../../hooks/useAnalytics'
import { formatRange, type DateRange } from '../../utils/analyticsPeriod'

/** Шапка и подписи (как и `FIELD_MAX_CHARS` на сервере). */
const FIELD_MAX = 200
/** Организация и подписант меняются редко — помним их в браузере. */
const STORAGE_KEY = 'uk_official_report_v1'

function loadSaved(): Partial<OfficialReportOptions> {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '{}') as Partial<OfficialReportOptions>
  } catch {
    return {}
  }
}

function save(opts: OfficialReportOptions) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(opts))
  } catch {
    // приватный режим / квота — просто не запоминаем
  }
}

export default function OfficialReportDialog({ range }: { range: DateRange | null }) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [opts, setOpts] = useState<OfficialReportOptions>(() => {
    const saved = loadSaved()
    return {
      lang: saved.lang === 'uz' ? 'uz' : 'ru',
      organization: saved.organization ?? '',
      signer: saved.signer ?? '',
    }
  })

  const submit = async () => {
    if (!range) return
    const clean = { ...opts, organization: opts.organization.trim(), signer: opts.signer.trim() }
    setBusy(true)
    try {
      await exportOfficialReport(range, clean)
      save(clean)
      setOpen(false)
    } catch {
      toast.error(t('analytics.exportFailed'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <Button size="sm" variant="outline" disabled={!range} onClick={() => setOpen(true)}>
        <FileSpreadsheet size={14} /> {t('analytics.official.button')}
      </Button>
      <Dialog open={open} onOpenChange={o => { if (!busy) setOpen(o) }}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>{t('analytics.official.title')}</DialogTitle>
            <DialogDescription>{t('analytics.official.description')}</DialogDescription>
          </DialogHeader>

          <div className="flex flex-col gap-3">
            {range && (
              <p className="text-[13px] text-text-secondary">
                {t('analytics.official.period')}:{' '}
                <span className="font-[family-name:var(--font-mono)]">{formatRange(range)}</span>
              </p>
            )}
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="official-org">{t('analytics.official.organization')}</Label>
              <Input
                id="official-org"
                maxLength={FIELD_MAX}
                placeholder={t('analytics.official.organizationPlaceholder')}
                value={opts.organization}
                onChange={e => setOpts({ ...opts, organization: e.target.value })}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="official-signer">{t('analytics.official.signer')}</Label>
              <Input
                id="official-signer"
                maxLength={FIELD_MAX}
                placeholder={t('analytics.official.signerPlaceholder')}
                value={opts.signer}
                onChange={e => setOpts({ ...opts, signer: e.target.value })}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="official-lang">{t('analytics.official.language')}</Label>
              <Select
                id="official-lang"
                value={opts.lang}
                onChange={e => setOpts({ ...opts, lang: e.target.value === 'uz' ? 'uz' : 'ru' })}
              >
                <option value="ru">{t('analytics.official.langRu')}</option>
                <option value="uz">{t('analytics.official.langUz')}</option>
              </Select>
            </div>
            <p className="text-[12px] text-text-muted">{t('analytics.official.contents')}</p>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)} disabled={busy}>
              {t('common.cancel')}
            </Button>
            <Button onClick={submit} disabled={busy || !range}>
              {busy ? t('analytics.official.preparing') : t('analytics.official.download')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
