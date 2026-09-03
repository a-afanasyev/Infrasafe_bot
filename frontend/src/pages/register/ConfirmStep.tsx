import type { FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { Button } from '../../components/ui/button'
import { Input } from '../../components/ui/input'
import { Label } from '../../components/ui/label'

interface Props {
  fullName: string
  onFullNameChange: (v: string) => void
  phone: string
  addressLabel: string
  onChangeAddress: () => void
  onSubmit: () => Promise<void> | void
  submitting: boolean
  error: string
}

/** Итог: ФИО (редактируемое), телефон и адрес (только чтение), отправка. */
export function ConfirmStep({
  fullName, onFullNameChange, phone, addressLabel, onChangeAddress, onSubmit, submitting, error,
}: Props) {
  const { t } = useTranslation()
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
      {error && <div className="text-[13px] text-red font-[family-name:var(--font-body)]">{error}</div>}
      <Button type="submit" disabled={submitting} className="w-full">
        {submitting ? t('common.sending') : t('register.submit')}
      </Button>
    </form>
  )
}
