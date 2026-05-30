import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { Label } from '../components/ui/label'
import { Select } from '../components/ui/select'
import { useRegistration, type RegistrationApartment } from '../hooks/useRegistration'

type Phase = 'loading' | 'no_telegram' | 'form' | 'pending' | 'already_registered'

function apartmentLabel(a: RegistrationApartment): string {
  return [a.yard_name, a.building_address, a.apartment_number ? `кв ${a.apartment_number}` : null]
    .filter(Boolean)
    .join(' · ')
}

function getDetail(err: unknown): string | undefined {
  return (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
}

function getStatus(err: unknown): number | undefined {
  return (err as { response?: { status?: number } })?.response?.status
}

export default function RegisterPage() {
  const { t } = useTranslation()
  const { initData, start, submit } = useRegistration()

  const [phase, setPhase] = useState<Phase>('loading')
  const [ticket, setTicket] = useState<string>('')
  const [apartments, setApartments] = useState<RegistrationApartment[]>([])
  const [fullName, setFullName] = useState('')
  const [phone, setPhone] = useState('')
  const [apartmentId, setApartmentId] = useState<string>('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const startedRef = useRef(false)

  async function runStart(): Promise<boolean> {
    setError('')
    try {
      const data = await start()
      setTicket(data.registration_ticket)
      setApartments(data.apartments)
      const name = [data.prefill.first_name, data.prefill.last_name].filter(Boolean).join(' ')
      setFullName((prev) => prev || name)
      setPhone((prev) => prev || data.prefill.phone || '')
      setApartmentId((prev) => prev || (data.apartments[0] ? String(data.apartments[0].id) : ''))
      setPhase('form')
      return true
    } catch (err: unknown) {
      const status = getStatus(err)
      if (status === 409) {
        const detail = getDetail(err)
        // "already approved" → user already has an account.
        if (!detail || /approv|одобр|уже/i.test(detail)) {
          setPhase('already_registered')
        } else {
          setError(detail)
          setPhase('form')
        }
        return false
      }
      setError(getDetail(err) || t('register.error_generic'))
      setPhase('form')
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

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    if (!apartmentId) {
      setError(t('register.apartment'))
      return
    }
    setSubmitting(true)
    try {
      const data = await submit(ticket, {
        full_name: fullName.trim(),
        phone: phone.trim(),
        apartment_id: Number(apartmentId),
      })
      if (data.status === 'pending') setPhase('pending')
    } catch (err: unknown) {
      const status = getStatus(err)
      const detail = getDetail(err)
      if (status === 401) {
        // Ticket expired — re-run start() and ask to resubmit.
        const ok = await runStart()
        if (ok) setError(t('register.error_generic'))
      } else if (status === 409) {
        if (detail && /approv|одобр|уже/i.test(detail)) {
          setPhase('already_registered')
        } else {
          setError(detail || t('register.error_generic'))
        }
      } else if (status === 400 || status === 422) {
        setError(detail || t('register.error_generic'))
      } else {
        setError(detail || t('register.error_generic'))
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-bg-root px-4">
      <div className="w-full max-w-[400px]">
        <div className="flex flex-col items-center mb-7">
          <img
            src={`${import.meta.env.BASE_URL}infrasafe-logo.svg`}
            alt="InfraSafe"
            className="w-[52px] h-[52px] mb-3 rounded-full shadow-[0_0_32px_rgba(0,212,170,0.3)]"
          />
          <div className="font-[family-name:var(--font-display)] font-bold text-[22px] text-text-primary tracking-tight">
            {t('register.title')}
          </div>
        </div>

        <div className="bg-bg-card border border-white/[.08] rounded-2xl p-8 px-7 shadow-[0_32px_80px_rgba(0,0,0,0.5),0_0_0_1px_rgba(0,212,170,0.05)]">
          {phase === 'loading' && (
            <div className="text-center text-sm text-text-secondary font-[family-name:var(--font-body)]">
              {t('common.loading')}
            </div>
          )}

          {phase === 'no_telegram' && (
            <div className="text-center text-sm text-text-secondary font-[family-name:var(--font-body)]">
              {t('register.open_in_telegram')}
            </div>
          )}

          {phase === 'already_registered' && (
            <div className="flex flex-col gap-4 text-center">
              <div className="text-sm text-text-secondary font-[family-name:var(--font-body)]">
                {t('register.already_registered')}
              </div>
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
              <div className="text-sm text-text-secondary font-[family-name:var(--font-body)]">
                {t('register.pending_body')}
              </div>
            </div>
          )}

          {phase === 'form' && (
            <form onSubmit={handleSubmit} className="flex flex-col gap-4">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="reg-full-name">{t('register.full_name')}</Label>
                <Input
                  id="reg-full-name"
                  type="text"
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  required
                  autoComplete="name"
                />
              </div>

              <div className="flex flex-col gap-1.5">
                <Label htmlFor="reg-phone">{t('register.phone')}</Label>
                <Input
                  id="reg-phone"
                  type="tel"
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                  required
                  autoComplete="tel"
                />
              </div>

              <div className="flex flex-col gap-1.5">
                <Label htmlFor="reg-apartment">{t('register.apartment')}</Label>
                <Select
                  id="reg-apartment"
                  value={apartmentId}
                  onChange={(e) => setApartmentId(e.target.value)}
                  required
                >
                  {apartments.length === 0 && <option value="" />}
                  {apartments.map((a) => (
                    <option key={a.id} value={String(a.id)}>
                      {apartmentLabel(a)}
                    </option>
                  ))}
                </Select>
              </div>

              {error && (
                <div className="text-[13px] text-[#f87171] font-[family-name:var(--font-body)]">
                  {error}
                </div>
              )}

              <Button type="submit" disabled={submitting} className="w-full">
                {submitting ? t('common.sending') : t('register.submit')}
              </Button>
            </form>
          )}
        </div>
      </div>
    </div>
  )
}
