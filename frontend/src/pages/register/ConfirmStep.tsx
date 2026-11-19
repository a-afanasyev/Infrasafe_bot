import { useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { Button } from '../../components/ui/button'
import { Input } from '../../components/ui/input'
import { Label } from '../../components/ui/label'

interface Props {
  fullName: string
  onFullNameChange: (v: string) => void
  phone: string
  addressLabel: string
  /** Название оператора для текста согласия. */
  company: string
  onChangeAddress: () => void
  onSubmit: () => Promise<void> | void
  submitting: boolean
  error: string
}

/** Итог: ФИО (редактируемое), телефон и адрес (только чтение), согласие на обработку ПДн, отправка. */
export function ConfirmStep({
  fullName, onFullNameChange, phone, addressLabel, company, onChangeAddress, onSubmit, submitting, error,
}: Props) {
  const { t } = useTranslation()
  const [consent, setConsent] = useState(false)
  const muted = 'text-sm text-text-secondary font-[family-name:var(--font-body)]'

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    void onSubmit()
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="reg-full-name">{t('register.full_name')}</Label>
        <Input
          id="reg-full-name"
          type="text"
          value={fullName}
          onChange={(e) => onFullNameChange(e.target.value)}
          required
          autoComplete="name"
        />
      </div>
      <div className="flex flex-col gap-1">
        <div className={muted}>{t('register.phone')}</div>
        <div className="text-text-primary">{phone}</div>
      </div>
      <div className="flex flex-col gap-1">
        <div className={muted}>{t('register.address')}</div>
        <div className="text-text-primary">{addressLabel}</div>
        <Button type="button" variant="outline" className="w-full mt-1" onClick={onChangeAddress}>
          {t('register.change_address')}
        </Button>
      </div>
      <label className={`${muted} flex items-start gap-2 cursor-pointer`}>
        <input
          type="checkbox"
          className="mt-0.5 h-4 w-4 shrink-0 accent-[var(--accent)]"
          checked={consent}
          onChange={(e) => setConsent(e.target.checked)}
          required
        />
        <span>{t('register.consent_label')}</span>
      </label>
      <details className={muted}>
        <summary className="cursor-pointer">{t('register.consent_details')}</summary>
        <div className="mt-2 whitespace-pre-line">{t('register.consent_text', { company })}</div>
      </details>
      {error && <div className="text-[13px] text-red font-[family-name:var(--font-body)]">{error}</div>}
      <Button type="submit" disabled={submitting || !consent} className="w-full">
        {submitting ? t('common.sending') : t('register.submit')}
      </Button>
    </form>
  )
}
