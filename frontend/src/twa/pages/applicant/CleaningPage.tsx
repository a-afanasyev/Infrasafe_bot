import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { useNavigate } from 'react-router'
import { useTranslation } from 'react-i18next'
import { ChevronLeft } from 'lucide-react'
import { twaClient } from '../../twaClient'
import {
  publicCleaningPhotoUrl,
  usePublicCleaningBuilding,
} from '../../../hooks/usePublicCleaning'
import { useResidentBuildings } from '../../hooks/useResidentBuildings'

/**
 * Уборка в доме жителя (/twa/app/cleaning): подъезды сегодня, график недели,
 * «Сообщить: не убрано». Дом берётся из адресов жителя; данные — открытая
 * сводка, жалоба — авторизованный запрос (только на свой дом).
 */
const time = (iso: string | null) => (iso ? new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '')

export default function ResidentCleaningPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const buildings = useResidentBuildings()
  const [selected, setSelected] = useState<number | null>(null)
  const buildingId = selected ?? buildings.data?.[0]?.id ?? null
  const view = usePublicCleaningBuilding(buildingId)
  const [sent, setSent] = useState<Record<number, string>>({})
  const complain = useMutation({
    mutationFn: (entrance: number) =>
      twaClient.post('/api/v2/cleaning/complaints', { building_id: buildingId, entrance }).then((r) => r.data),
    onSuccess: (data, entrance) => setSent((prev) => ({ ...prev, [entrance]: data.request_number ?? '' })),
  })

  return (
    <div className="min-h-screen bg-gray-50 p-4 pb-24 dark:bg-gray-950">
      <button type="button" onClick={() => navigate('/twa/app')} className="mb-2 flex h-11 items-center gap-1 text-[14px] font-semibold text-gray-900 dark:text-gray-100">
        <ChevronLeft size={20} aria-hidden /> {t('twa.residentCleaning.back')}
      </button>
      <h1 className="mb-3 text-lg font-bold text-gray-900 dark:text-gray-100">{t('twa.residentCleaning.title')}</h1>

      {(buildings.data?.length ?? 0) > 1 && (
        <select
          aria-label={t('twa.residentCleaning.building')} value={buildingId ?? ''}
          onChange={(e) => setSelected(Number(e.target.value))}
          className="mb-3 h-11 w-full rounded-xl border border-gray-300 bg-white px-3 text-[14px] text-gray-900 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100"
        >
          {buildings.data?.map((b) => <option key={b.id} value={b.id}>{b.label}</option>)}
        </select>
      )}

      {(view.isError || (buildings.isSuccess && buildingId === null)) && (
        <p className="rounded-2xl bg-white p-4 text-[14px] text-gray-600 dark:bg-gray-800 dark:text-gray-300">{t('twa.residentCleaning.hidden')}</p>
      )}

      {view.data && (
        <>
          <section className="mb-3 rounded-2xl border border-gray-100 bg-white p-4 dark:border-gray-700 dark:bg-gray-800">
            <h2 className="mb-2 text-[15px] font-semibold text-gray-900 dark:text-gray-100">{t('twa.residentCleaning.today')} · {view.data.address}</h2>
            <ul className="flex flex-col gap-2">
              {view.data.entrances.map((entrance) => (
                <li key={entrance.entrance} className="list-none rounded-xl border border-gray-200 p-3 dark:border-gray-700">
                  <div className="flex items-center justify-between gap-2 text-[14px] text-gray-900 dark:text-gray-100">
                    <strong>{t('twa.residentCleaning.entrance', { n: entrance.entrance })}</strong>
                    <span className={entrance.state === 'done' ? 'font-semibold text-emerald-700 dark:text-emerald-400' : 'text-gray-600 dark:text-gray-300'}>
                      {entrance.state === 'done'
                        ? t('twa.residentCleaning.doneAt', { time: time(entrance.done_at) })
                        : t(`twa.residentCleaning.state.${entrance.state}`)}
                    </span>
                  </div>
                  {entrance.photo_ids.length > 0 && (
                    <div className="mt-2 grid grid-cols-3 gap-2">
                      {entrance.photo_ids.map((id) => (
                        <img key={id} src={publicCleaningPhotoUrl(id)} alt={t('twa.residentCleaning.photoAlt', { n: entrance.entrance })} className="h-20 w-full rounded-lg object-cover" />
                      ))}
                    </div>
                  )}
                  {entrance.state !== 'none' && (
                    sent[entrance.entrance] !== undefined ? (
                      <p role="status" className="mt-2 text-[13px] text-emerald-700 dark:text-emerald-400">
                        {sent[entrance.entrance]
                          ? t('twa.residentCleaning.sentWithNumber', { number: sent[entrance.entrance] })
                          : t('twa.residentCleaning.sent')}
                      </p>
                    ) : (
                      <button
                        type="button" disabled={complain.isPending} onClick={() => complain.mutate(entrance.entrance)}
                        className="mt-2 h-11 w-full rounded-xl border border-gray-400 text-[14px] font-semibold text-gray-900 disabled:opacity-60 dark:border-gray-500 dark:text-gray-100"
                      >
                        {t('twa.residentCleaning.complain')}
                      </button>
                    )
                  )}
                </li>
              ))}
            </ul>
            {complain.isError && <p role="alert" className="mt-2 text-[13px] text-red-700 dark:text-red-400">{t('twa.residentCleaning.complainError')}</p>}
          </section>

          <section className="rounded-2xl border border-gray-100 bg-white p-4 dark:border-gray-700 dark:bg-gray-800">
            <h2 className="mb-2 text-[15px] font-semibold text-gray-900 dark:text-gray-100">{t('twa.residentCleaning.schedule')}</h2>
            <ul className="flex flex-col">
              {view.data.week.map((works, day) => (
                <li key={day} className="flex list-none justify-between gap-3 border-b border-gray-100 py-2 text-[13px] text-gray-900 last:border-0 dark:border-gray-700 dark:text-gray-100">
                  <span>{t(`twa.residentCleaning.day.${day}`)}</span>
                  <span className={works.length ? 'text-right font-semibold' : 'text-gray-500 dark:text-gray-400'}>
                    {works.length === 0
                      ? t('twa.residentCleaning.dayOff')
                      : works.map((w) => t(`twa.cleaning.work.${w.work_kind}`) + (w.floor_from ? ` ${w.floor_from === w.floor_to ? w.floor_from : `${w.floor_from}–${w.floor_to}`}` : '') + (w.entrances ? ` (${t('cleaning.staff.entrancesList', { list: w.entrances.join(', ') })})` : '')).join(', ')}
                  </span>
                </li>
              ))}
            </ul>
          </section>
        </>
      )}
    </div>
  )
}
