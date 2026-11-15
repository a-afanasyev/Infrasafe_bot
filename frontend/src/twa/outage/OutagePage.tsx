import { useCallback, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router'
import { useTranslation } from 'react-i18next'
import { ArrowRight, Check, Droplets, Flame } from 'lucide-react'
import { useTelegramSDK } from '../hooks/useTelegramSDK'
import { useBackTo } from '../simple/hooks/useSimpleNav'
import { ConfirmSheet, ErrorBlock, Loading, PRIMARY_BTN, SECONDARY_BTN } from '../simple/components/Ui'
import { FlashScreen, useFlash } from '../simple/components/Flash'
import {
  OUTAGES_KEY, OUTAGE_DURATIONS, OUTAGE_RESOURCES, announceOutage, outageErrorKey, useOutageOptions,
  type OutageDuration, type OutageResource,
} from './api'

type Step = 'resource' | 'buildings' | 'duration'
const ICONS = { water: Droplets, heating: Flame } as const

/**
 * «Отключил воду»: один вопрос на экран — что, какие дома, на сколько, «Да / Нет».
 * Общий экран TWA исполнителя и простого режима. Офлайн-очереди нет намеренно:
 * объявление должно уйти сразу или показать ошибку.
 */
export default function OutagePage({ backTo }: { backTo: string }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { notify } = useTelegramSDK()
  // isPending, не isLoading: пока ждём текущую смену, запрос ещё не начат — это тоже «загрузка».
  const { data, isPending: isLoading, isError, refetch } = useOutageOptions()
  const [step, setStep] = useState<Step>('resource')
  const [resource, setResource] = useState<OutageResource>('water')
  const [buildings, setBuildings] = useState<number[]>([])
  const [duration, setDuration] = useState<OutageDuration | null>(null)
  const [flash, setFlash] = useFlash()

  // «Назад» Telegram — на шаг назад, с первого шага — на экран смены.
  const stepBack = useCallback(() => {
    if (step === 'resource') return false
    setStep(step === 'duration' ? 'buildings' : 'resource')
    return true
  }, [step])
  useBackTo(backTo, stepBack)

  const announce = useMutation({
    mutationFn: () => announceOutage({ resource, building_ids: buildings, duration: duration! }),
    onSuccess: () => {
      notify('success')
      void queryClient.invalidateQueries({ queryKey: OUTAGES_KEY })
      navigate(backTo, { replace: true })
    },
    onError: (err: unknown) => {
      notify('error')
      setDuration(null)
      setFlash({ ok: false, title: t(outageErrorKey(err)) })
    },
  })

  if (isLoading) return <main className="p-3"><Loading /></main>
  if (isError || !data) return <main className="p-3"><ErrorBlock onRetry={() => void refetch()} /></main>
  if (!data.allowed) {
    return (
      <main className="p-3 pt-12 text-center" role="alert">
        <p className="text-[22px] font-bold">{t(`twa.outage.error.${data.reason === 'no_active_shift' ? 'no_active_shift' : 'not_plumber'}`)}</p>
      </main>
    )
  }

  const toggle = (id: number) => setBuildings((prev) => (prev.includes(id) ? prev.filter((b) => b !== id) : [...prev, id]))
  const addresses = data.yards.flatMap((y) => y.buildings).filter((b) => buildings.includes(b.id)).map((b) => b.address)

  return (
    <main className="p-3 pb-28 flex flex-col gap-3">
      <h1 className="text-[24px] font-bold text-center py-2">{t(`twa.outage.ask.${step}`)}</h1>

      {step === 'resource' && OUTAGE_RESOURCES.map((r) => {
        const Icon = ICONS[r]
        return (
          <button key={r} type="button" onClick={() => { setResource(r); setStep('buildings') }}
                  className={`${PRIMARY_BTN} h-[96px] bg-white dark:bg-gray-800 border-2 border-gray-200 dark:border-gray-700`}>
            <Icon size={36} className="text-sky-600" aria-hidden /> {t(`twa.outage.resource.${r}`)}
          </button>
        )
      })}

      {step === 'buildings' && (
        <>
          {data.yards.map((yard) => (
            <section key={yard.id} className="flex flex-col gap-2">
              {data.yards.length > 1 && <h2 className="text-[16px] font-semibold uppercase text-gray-500 pt-2">{yard.name}</h2>}
              {yard.buildings.map((b) => {
                const on = buildings.includes(b.id)
                return (
                  <button key={b.id} type="button" aria-pressed={on} onClick={() => toggle(b.id)}
                          className={`${SECONDARY_BTN} justify-start px-4 border-2 ${on ? 'bg-sky-600 border-sky-600 text-white' : 'bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700'}`}>
                    {on && <Check size={24} aria-hidden />} {b.address}
                  </button>
                )
              })}
            </section>
          ))}
          <div className="fixed bottom-0 inset-x-0 p-3 pb-[calc(12px+env(safe-area-inset-bottom))] bg-gray-100/95 dark:bg-gray-950/95">
            <button type="button" disabled={buildings.length === 0} onClick={() => setStep('duration')} className={`${PRIMARY_BTN} bg-emerald-600 text-white`}>
              {t('twa.outage.next')} <ArrowRight size={28} aria-hidden />
            </button>
          </div>
        </>
      )}

      {step === 'duration' && OUTAGE_DURATIONS.map((d) => (
        <button key={d} type="button" onClick={() => setDuration(d)}
                className={`${PRIMARY_BTN} bg-white dark:bg-gray-800 border-2 border-gray-200 dark:border-gray-700`}>
          {t(`twa.outage.duration.${d}`)}
        </button>
      ))}

      {duration && (
        <ConfirmSheet title={t('twa.outage.confirm')} busy={announce.isPending} onNo={() => setDuration(null)} onYes={() => announce.mutate()}>
          <p className="text-[20px] font-semibold text-center">
            {t(`twa.outage.resource.${resource}`)} · {t(`twa.outage.duration.${duration}`)}
          </p>
          <p className="text-[18px] text-center">{addresses.join(', ')}</p>
          <p className="text-[16px] text-center text-gray-600 dark:text-gray-300">{t('twa.outage.confirmHint')}</p>
        </ConfirmSheet>
      )}
      <FlashScreen flash={flash} onClose={() => setFlash(null)} />
    </main>
  )
}
