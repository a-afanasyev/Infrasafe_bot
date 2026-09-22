import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Button } from '../components/ui/button'
import { useRegistration, type RegistrationApartment } from '../hooks/useRegistration'
import { usePageTitle } from '../hooks/usePageTitle'
import { brand } from '../brand/brand'
import { ContactStep } from './register/ContactStep'
import { AddressCascade, type AddressLabels } from './register/AddressCascade'
import { ConfirmStep } from './register/ConfirmStep'
import { apiErrorCode, apiErrorDetail, apiErrorStatus, safeErrorMessage } from '../utils/errorMessage'

// Спека 2026-09-03 §5.1: contact → address → confirm → pending.
// Контакт — только через Telegram (requestContact), квартира — каскадом
// двор → дом → квартира, как в боте.
type Phase =
  | 'loading'
  | 'no_telegram'
  | 'contact'
  | 'address'
  | 'confirm'
  | 'pending'
  | 'already_registered'

interface SelectedAddress {
  apartment: RegistrationApartment
  labels: AddressLabels
}

// A9-P3-20: машинные коды 409 регистрации (заголовок X-Error-Code,
// uk_management_bot/api/registration/router.py) — ветвимся по ним, а не regex
// по тексту detail: правка формулировки на бэке ломала сценарий.
const CODE_ALREADY_REGISTERED = 'already_registered'
const CODE_ALREADY_RESIDENT = 'already_resident'
const CODE_CONTACT_REQUIRED = 'contact_required'

/**
 * Код 409 для ветвления. Если заголовка X-Error-Code нет (старый бэкенд во
 * время неатомарной раскатки или заголовок вырезан по пути) — фолбэк на
 * прежнее ветвление по тексту detail, чтобы UX не деградировал до generic.
 */
function submitConflictCode(err: unknown): string | null {
  const code = apiErrorCode(err)
  if (code) return code
  const detail = apiErrorDetail(err)
  if (!detail) return null
  if (/контакт|kontakt/i.test(detail)) return CODE_CONTACT_REQUIRED
  if (/уже подтверждены|already/i.test(detail)) return CODE_ALREADY_REGISTERED
  return null
}

export default function RegisterPage() {
  const { t } = useTranslation()
  usePageTitle(t('register.title')) // QA-03: иначе document.title оставался от предыдущей страницы
  const reg = useRegistration()
  const { initData, start, submit } = reg

  const [phase, setPhase] = useState<Phase>('loading')
  const [ticket, setTicket] = useState('')
  const [fullName, setFullName] = useState('')
  const [phone, setPhone] = useState('')
  const [selected, setSelected] = useState<SelectedAddress | null>(null)
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const startedRef = useRef(false)

  // A9-P3-20: «кв» — через i18n (было захардкожено по-русски и в UZ).
  function addressLabel(sel: SelectedAddress): string {
    return [sel.labels.yard, sel.labels.building, t('register.apartment_label', { number: sel.apartment.apartment_number })]
      .filter(Boolean)
      .join(' · ')
  }

  async function runStart(): Promise<boolean> {
    setError('')
    try {
      const data = await start()
      setTicket(data.registration_ticket)
      const name = [data.prefill.first_name, data.prefill.last_name].filter(Boolean).join(' ')
      setFullName((prev) => prev || name)
      const knownPhone = data.prefill.phone || ''
      setPhone((prev) => prev || knownPhone)
      // Телефон уже оставлен в боте — шаг контакта не нужен.
      setPhase(knownPhone || phone ? 'address' : 'contact')
      return true
    } catch (err: unknown) {
      if (apiErrorStatus(err) === 409) {
        // У /start единственный 409 — «уже зарегистрирован»; без кода (старый
        // бэк) трактуем так же.
        const code = apiErrorCode(err)
        if (code === null || code === CODE_ALREADY_REGISTERED) {
          setPhase('already_registered')
        } else {
          setError(safeErrorMessage(err, t('register.error_generic')))
          setPhase('contact')
        }
        return false
      }
      setError(safeErrorMessage(err, t('register.error_generic')))
      setPhase('contact')
      return false
    }
  }

  useEffect(() => {
    // initData starts as '' and is populated once the Telegram SDK is ready.
    // Wait a tick for it; if it never arrives, prompt to open in Telegram.
    if (startedRef.current) return
    if (initData) {
      startedRef.current = true
      void runStart()
      return
    }
    const timeout = window.setTimeout(() => {
      if (!startedRef.current && !initData) setPhase('no_telegram')
    }, 1500)
    return () => window.clearTimeout(timeout)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initData])

  function onContactDone(p: string) {
    setPhone(p)
    setPhase('address')
  }

  function onAddressSelected(apartment: RegistrationApartment, labels: AddressLabels) {
    setSelected({ apartment, labels })
    setPhase('confirm')
  }

  async function handleSubmit() {
    setError('')
    if (!selected) {
      setPhase('address')
      return
    }
    setSubmitting(true)
    try {
      await submit(ticket, { full_name: fullName.trim(), apartment_id: selected.apartment.id })
      setPhase('pending')
    } catch (err: unknown) {
      const status = apiErrorStatus(err)
      const code = status === 409 ? submitConflictCode(err) : null
      const message = safeErrorMessage(err, t('register.error_generic'))
      if (status === 401) {
        // Ticket expired (30 min) → fetch a fresh one and let the user resubmit.
        await runStart()
        setPhase('confirm')
        setError(message)
      } else if (code === CODE_CONTACT_REQUIRED) {
        // Телефон в БД не появился — вернуть на шаг контакта.
        setPhone('')
        setPhase('contact')
        setError(t('register.phone_required'))
      } else if (code === CODE_ALREADY_REGISTERED || code === CODE_ALREADY_RESIDENT) {
        setPhase('already_registered')
      } else {
        setError(message)
      }
    } finally {
      setSubmitting(false)
    }
  }

  const muted = 'text-center text-sm text-text-secondary font-[family-name:var(--font-body)]'

  return (
    <div className="min-h-screen flex items-center justify-center bg-bg-root px-4">
      <div className="w-full max-w-[400px]">
        <div className="flex flex-col items-center mb-7">
          <img
            src={`${import.meta.env.BASE_URL}${brand.logoMark}`}
            alt={brand.displayName}
            className="w-[52px] h-[52px] mb-3 rounded-full shadow-[var(--auth-logo-shadow)]"
          />
          <div className="font-[family-name:var(--font-display)] font-bold text-[22px] text-text-primary tracking-tight">
            {t('register.title')}
          </div>
        </div>
        <div className="bg-bg-card border border-[color:var(--auth-card-border)] rounded-2xl p-8 px-7 shadow-[var(--auth-card-shadow)]">
          {phase === 'loading' && <div className={muted}>{t('common.loading')}</div>}
          {phase === 'no_telegram' && <div className={muted}>{t('register.open_in_telegram')}</div>}
          {phase === 'already_registered' && (
            <div className="flex flex-col gap-4 text-center">
              <div className={muted}>{t('register.already_registered')}</div>
              <a href={`${import.meta.env.BASE_URL}`}>
                <Button type="button" className="w-full">
                  {t('common.goHome')}
                </Button>
              </a>
            </div>
          )}
          {phase === 'pending' && (
            <div className="flex flex-col gap-2 text-center">
              <div className="font-[family-name:var(--font-display)] font-bold text-text-primary">
                {t('register.pending_title')}
              </div>
              <div className={muted}>{t('register.pending_body')}</div>
            </div>
          )}
          {phase === 'contact' && (
            <>
              {error && <div className="text-[13px] text-red mb-3 text-center">{error}</div>}
              <ContactStep ticket={ticket} contactStatus={reg.contactStatus} onDone={onContactDone} />
            </>
          )}
          {phase === 'address' && (
            <AddressCascade
              ticket={ticket}
              api={{ yards: reg.yards, buildings: reg.buildings, apartments: reg.apartments }}
              onSelect={onAddressSelected}
            />
          )}
          {phase === 'confirm' && selected && (
            <ConfirmStep
              fullName={fullName}
              onFullNameChange={setFullName}
              phone={phone}
              addressLabel={addressLabel(selected)}
              onChangeAddress={() => setPhase('address')}
              onSubmit={handleSubmit}
              submitting={submitting}
              error={error}
            />
          )}
        </div>
      </div>
    </div>
  )
}
