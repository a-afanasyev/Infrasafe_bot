import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { FileSpreadsheet } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select } from '@/components/ui/select'
import { brand } from '../../brand/brand'
import { useBoardConfig } from '../../hooks/useBoardConfig'
import { REPORT_SHEETS, exportOfficialReport, type ReportSheet } from '../../hooks/useAnalytics'
import { logoToPngBase64 } from '../../utils/logoPng'
import { readStorage, writeStorage } from '../../utils/safeStorage'
import type { DateRange } from '../../utils/analyticsPeriod'
import { Panel } from './shared'

/** Шапка и подписи (как и `FIELD_MAX_CHARS` на сервере). */
const FIELD_MAX = 200
/** Подписант и правленое название меняются редко — помним их в браузере. */
const STORAGE_KEY = 'uk_official_report_v2'
/** Тот же логотип, что на странице жителей (`ResidentHomePage`). */
const LOGO_SRC = `${import.meta.env.BASE_URL}${brand.logoMark}`

type Lang = 'ru' | 'uz'

interface Saved {
  lang: Lang
  /** null — название не правили, берём из витрины на языке отчёта. */
  organization: string | null
  signer: string
}

function loadSaved(): Saved {
  try {
    const raw = JSON.parse(readStorage(STORAGE_KEY) ?? '{}') as Partial<Saved>
    return {
      lang: raw.lang === 'uz' ? 'uz' : 'ru',
      organization: typeof raw.organization === 'string' ? raw.organization : null,
      signer: typeof raw.signer === 'string' ? raw.signer : '',
    }
  } catch {
    return { lang: 'ru', organization: null, signer: '' }
  }
}

export default function ReportExportPanel({ range }: { range: DateRange }) {
  const { t } = useTranslation()
  const board = useBoardConfig()
  const [saved, setSaved] = useState<Saved>(loadSaved)
  const [sheets, setSheets] = useState<ReportSheet[]>([...REPORT_SHEETS])
  const [withLogo, setWithLogo] = useState(true)
  const [busy, setBusy] = useState(false)

  const organization = saved.organization ?? board.data?.org.name[saved.lang] ?? ''

  const update = (patch: Partial<Saved>) => setSaved(prev => ({ ...prev, ...patch }))
  const toggleSheet = (key: ReportSheet) =>
    setSheets(prev => (prev.includes(key) ? prev.filter(s => s !== key) : [...prev, key]))

  const submit = async () => {
    setBusy(true)
    try {
      const logo = withLogo ? await logoToPngBase64(LOGO_SRC) : null
      await exportOfficialReport(range, {
        lang: saved.lang,
        organization: organization.trim(),
        signer: saved.signer.trim(),
        sheets: REPORT_SHEETS.filter(s => sheets.includes(s)),
        logo,
      })
      writeStorage(STORAGE_KEY, JSON.stringify(saved))
    } catch {
      toast.error(t('analytics.exportFailed'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Panel title={t('analytics.official.title')}>
      <p className="text-[13px] text-text-secondary mb-4">{t('analytics.official.description')}</p>
      <div className="grid gap-4 md:grid-cols-2">
        <div className="flex flex-col gap-3">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="official-org">{t('analytics.official.organization')}</Label>
            <Input
              id="official-org"
              maxLength={FIELD_MAX}
              placeholder={t('analytics.official.organizationPlaceholder')}
              value={organization}
              onChange={e => update({ organization: e.target.value })}
            />
            <span className="text-[11px] text-text-muted">{t('analytics.official.organizationHint')}</span>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="official-signer">{t('analytics.official.signer')}</Label>
            <Input
              id="official-signer"
              maxLength={FIELD_MAX}
              placeholder={t('analytics.official.signerPlaceholder')}
              value={saved.signer}
              onChange={e => update({ signer: e.target.value })}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="official-lang">{t('analytics.official.language')}</Label>
            <Select
              id="official-lang"
              value={saved.lang}
              onChange={e => update({ lang: e.target.value === 'uz' ? 'uz' : 'ru' })}
            >
              <option value="ru">{t('analytics.official.langRu')}</option>
              <option value="uz">{t('analytics.official.langUz')}</option>
            </Select>
          </div>
        </div>

        <div className="flex flex-col gap-3">
          <fieldset className="flex flex-col gap-1.5">
            <legend className="text-sm font-medium mb-1.5">{t('analytics.official.sheets')}</legend>
            {REPORT_SHEETS.map(key => (
              <label key={key} className="flex items-center gap-2 text-[13px] cursor-pointer">
                <input type="checkbox" checked={sheets.includes(key)} onChange={() => toggleSheet(key)} />
                {t(`analytics.official.sheet.${key}`)}
              </label>
            ))}
          </fieldset>
          <label className="flex items-center gap-2 text-[13px] cursor-pointer">
            <input type="checkbox" checked={withLogo} onChange={e => setWithLogo(e.target.checked)} />
            {t('analytics.official.logo')}
            <img src={LOGO_SRC} alt="" height={24} className="h-6 w-auto" />
          </label>
        </div>
      </div>

      <p className="text-[12px] text-text-muted mt-4">{t('analytics.official.contents')}</p>
      <div className="flex flex-wrap items-center gap-3 mt-3">
        <Button onClick={submit} disabled={busy || sheets.length === 0}>
          <FileSpreadsheet size={14} /> {busy ? t('analytics.official.preparing') : t('analytics.official.download')}
        </Button>
        {sheets.length === 0 && (
          <span className="text-[12px] text-red">{t('analytics.official.noSheets')}</span>
        )}
      </div>
    </Panel>
  )
}
