import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { Hand, Inbox, Play, Moon } from 'lucide-react'
import { tCategory } from '../../../i18n/apiMaps'
import { useTelegramSDK } from '../../hooks/useTelegramSDK'
import { notifyError } from '../../utils/errors'
import { claimRequest, usePool, type PoolResponse } from '../api'
import TaskTile from '../components/TaskTile'
import { SimpleTabs } from '../components/Chrome'
import { ErrorBlock, Loading, PRIMARY_BTN, SECONDARY_BTN } from '../components/Ui'
import { poolAddress } from '../model'

const POOL_KEY = ['twa', 'simple', 'pool'] as const

function detailOf(err: unknown): unknown {
  return (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
}

/** «Взять»: свободные заявки группы. Вне смены — только «Начать смену». */
export default function PoolPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { notify } = useTelegramSDK()
  const { data, isLoading, refetch } = usePool()

  const dropFromPool = (number: string) =>
    queryClient.setQueryData<PoolResponse>(POOL_KEY, (old) =>
      old ? { ...old, items: old.items.filter((i) => i.request_number !== number) } : old,
    )

  const claim = useMutation({
    mutationFn: (number: string) => claimRequest(number),
    onSuccess: (_, number) => {
      notify('success')
      toast.success(t('twa.simple.pool.claimed'))
      dropFromPool(number)
      queryClient.invalidateQueries({ queryKey: ['twa', 'executor-tasks'] })
    },
    onError: (err: unknown, number) => {
      notify('error')
      const detail = detailOf(err)
      if (detail === 'already_claimed') {
        // Гонка: другой исполнитель успел раньше — убираем плитку сразу.
        toast.error(t('twa.simple.pool.alreadyClaimed'))
        dropFromPool(number)
      } else if (detail === 'not_eligible') {
        toast.error(t('twa.simple.pool.notEligible'))
        void refetch()
      } else {
        notifyError(err, t('twa.simple.done.failed'))
      }
    },
  })

  let content
  if (data && !data.on_shift) {
    content = (
      <div className="flex flex-col items-center gap-5 py-12 text-center">
        <Moon size={72} className="text-gray-400" aria-hidden />
        <p className="text-[24px] font-bold">{t('twa.simple.pool.offShift')}</p>
        <button type="button" onClick={() => navigate('/twa/s/shift')} className={`${PRIMARY_BTN} bg-emerald-600 text-white`}>
          <Play size={30} aria-hidden /> {t('twa.simple.pool.startShift')}
        </button>
      </div>
    )
  } else if (data) {
    content = data.items.length === 0 ? (
      <div className="flex flex-col items-center gap-4 py-16 text-center">
        <Inbox size={72} className="text-gray-400" aria-hidden />
        <p className="text-[24px] font-bold">{t('twa.simple.pool.empty')}</p>
      </div>
    ) : (
      <ul className="flex flex-col gap-3">
        {data.items.map((item) => (
          <TaskTile
            key={item.request_number}
            requestNumber={item.request_number}
            category={item.category}
            address={poolAddress(item, t) || tCategory(item.category, t)}
            text={item.description_first_line ?? ''}
            urgency={item.urgency}
            photoMediaId={item.photo_media_id ?? null}
            action={
              <button
                type="button"
                disabled={claim.isPending}
                onClick={() => claim.mutate(item.request_number)}
                className={`${SECONDARY_BTN} bg-blue-600 text-white`}
              >
                <Hand size={26} aria-hidden /> {t('twa.simple.pool.claim')}
              </button>
            }
          />
        ))}
      </ul>
    )
  } else if (isLoading) {
    content = <Loading />
  } else {
    content = <ErrorBlock onRetry={() => void refetch()} />
  }

  return (
    <>
      <main className="p-3 pb-[160px]">{content}</main>
      <SimpleTabs />
    </>
  )
}
