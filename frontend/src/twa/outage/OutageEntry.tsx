import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router'
import { useTranslation } from 'react-i18next'
import { Check, Droplets } from 'lucide-react'
import { useTelegramSDK } from '../hooks/useTelegramSDK'
import { ConfirmSheet, PRIMARY_BTN } from '../simple/components/Ui'
import { FlashScreen, useFlash } from '../simple/components/Flash'
import { OUTAGES_KEY, closeOutage, outageErrorKey, useOutageOptions, type OutageNotice } from './api'

/**
 * Блок на экране смены. «Отключил воду» видит только сантехник: на смене —
 * рабочая, вне смены — неактивная с подсказкой «Сначала начните смену».
 * «Воду включили» — по каждому незакрытому отключению. Остальным — пусто.
 */
export default function OutageEntry({ to }: { to: string }) {
  const { t, i18n } = useTranslation()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { notify } = useTelegramSDK()
  const { data } = useOutageOptions()
  const [closing, setClosing] = useState<OutageNotice | null>(null)
  const [flash, setFlash] = useFlash()

  const close = useMutation({
    mutationFn: (id: number) => closeOutage(id),
    onSuccess: () => {
      notify('success')
      setFlash({ ok: true, title: t('twa.outage.closed') })
    },
    onError: (err: unknown) => {
      notify('error')
      setFlash({ ok: false, title: t(outageErrorKey(err)) })
    },
    onSettled: () => {
      setClosing(null)
      void queryClient.invalidateQueries({ queryKey: OUTAGES_KEY })
    },
  })

  if (!data) return null
  // Сервер отвечает not_plumber всем, кроме сантехника; no_active_shift — сантехнику вне смены.
  const plumber = data.allowed || data.reason === 'no_active_shift'
  if (!plumber && data.open.length === 0) return null
  const title = (n: OutageNotice) => (i18n.language.startsWith('uz') && n.title_uz) || n.title_ru
  return (
    <section className="w-full flex flex-col gap-3" data-testid="outage-entry">
      {data.open.map((n) => (
        <button key={n.id} type="button" onClick={() => setClosing(n)} className={`${PRIMARY_BTN} h-auto min-h-[72px] py-2 flex-col gap-0 bg-emerald-600 text-white`}>
          <span className="flex items-center gap-2"><Check size={28} aria-hidden /> {t(`twa.outage.restored.${n.resource === 'heating' ? 'heating' : 'water'}`)}</span>
          <span className="text-[16px] font-medium opacity-90">{title(n)}</span>
        </button>
      ))}
      {plumber && (
        <button type="button" disabled={!data.allowed} onClick={() => navigate(to)} className={`${PRIMARY_BTN} bg-sky-600 text-white`}>
          <Droplets size={30} aria-hidden /> {t('twa.outage.entry')}
        </button>
      )}
      {plumber && !data.allowed && (
        <p className="text-[18px] text-center text-gray-600 dark:text-gray-300">{t('twa.outage.error.no_active_shift')}</p>
      )}
      {closing && (
        <ConfirmSheet title={t('twa.outage.confirmClose')} busy={close.isPending} onNo={() => setClosing(null)} onYes={() => close.mutate(closing.id)}>
          <p className="text-[20px] font-semibold text-center">{title(closing)}</p>
          <p className="text-[18px] text-center text-gray-600 dark:text-gray-300">{t('twa.outage.closeHint')}</p>
        </ConfirmSheet>
      )}
      <FlashScreen flash={flash} onClose={() => setFlash(null)} />
    </section>
  )
}
