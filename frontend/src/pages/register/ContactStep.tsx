import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Button } from '../../components/ui/button'
import { useTelegramSDK } from '../../twa/hooks/useTelegramSDK'
import type { RegistrationContactStatus } from '../../hooks/useRegistration'
import { useContactPolling } from './useContactPolling'

interface Props {
  ticket: string
  contactStatus: (ticket: string) => Promise<RegistrationContactStatus>
  onDone: (phone: string) => void
}

/**
 * Шаг «Поделиться контактом»: телефон только через Telegram.WebApp.requestContact.
 * Ручного ввода нет — номер нельзя подделать, он совпадает с ботом.
 */
export function ContactStep({ ticket, contactStatus, onDone }: Props) {
  const { t } = useTranslation()
  const { tg } = useTelegramSDK()
  const [declined, setDeclined] = useState(false)
  const { state, start } = useContactPolling(ticket, contactStatus, onDone)

  const requestContact = tg?.requestContact

  function share() {
    if (!requestContact) return
    setDeclined(false)
    requestContact((sent) => {
      if (sent) start()
      else setDeclined(true)
    })
  }

  const body = 'text-sm text-text-secondary font-[family-name:var(--font-body)]'

  if (!requestContact) {
    return <div className={`text-center ${body}`}>{t('register.update_telegram')}</div>
  }

  return (
    <div className="flex flex-col gap-4 text-center">
      <div className="font-[family-name:var(--font-display)] font-bold text-text-primary">
        {t('register.contact_title')}
      </div>
      <div className={body}>{t('register.contact_hint')}</div>
      {state === 'polling' && <div className={body}>{t('register.contact_waiting')}</div>}
      {state === 'timeout' && (
        <>
          <div className={body}>{t('register.contact_timeout')}</div>
          <Button type="button" variant="outline" className="w-full" onClick={start}>
            {t('register.contact_retry')}
          </Button>
        </>
      )}
      {declined && <div className="text-[13px] text-red">{t('register.contact_declined')}</div>}
      {state !== 'polling' && (
        <Button type="button" className="w-full" onClick={share}>
          {t('register.share_contact')}
        </Button>
      )}
    </div>
  )
}
