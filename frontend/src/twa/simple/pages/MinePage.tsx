import { useMemo } from 'react'
import { useNavigate } from 'react-router'
import { useTranslation } from 'react-i18next'
import { Check, PartyPopper, XCircle } from 'lucide-react'
import { tCategory } from '../../../i18n/apiMaps'
import { useExecutorTasks } from '../../hooks/useExecutorTasks'
import TaskTile from '../components/TaskTile'
import { SimpleTabs } from '../components/Chrome'
import { ErrorBlock, Loading, SECONDARY_BTN } from '../components/Ui'
import { firstLine, queueMarks, returnReason, sortMine, tileState } from '../model'
import { FINAL_REASON_KEY, useCompletionQueue } from '../queue/CompletionQueue'
import type { QueueItem } from '../queue/types'

/** «Готово» не принято окончательно, а заявки в списке уже нет: крупная плашка. */
function LostTile({ item, onDismiss }: { item: QueueItem; onDismiss: () => void }) {
  const { t } = useTranslation()
  return (
    <li
      data-testid={`lost-${item.requestNumber}`}
      className="list-none rounded-2xl border-2 border-red-500 bg-red-50 dark:bg-red-950/40 p-4 flex flex-col gap-3"
    >
      <p className="flex items-center gap-3 text-[22px] font-bold text-red-700 dark:text-red-300">
        <XCircle size={32} className="shrink-0" aria-hidden />
        {item.failed ? t(FINAL_REASON_KEY[item.failed]) : null}
      </p>
      <p className="text-[20px] font-semibold break-words">
        {item.label || t('twa.simple.task.number', { number: item.requestNumber })}
      </p>
      <button type="button" onClick={onDismiss} className={`${SECONDARY_BTN} bg-white dark:bg-gray-900 border-2 border-red-500 text-red-700 dark:text-red-300`}>
        <Check size={26} aria-hidden /> {t('twa.simple.ok')}
      </button>
    </li>
  )
}

/** «Мои»: назначенные активные заявки — вернули → в работе → ждут менеджера. */
export default function MinePage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { data, isLoading, isError, refetch } = useExecutorTasks('active')
  const { items: queued, dismiss } = useCompletionQueue()
  const marks = useMemo(() => queueMarks(queued), [queued])
  const tasks = useMemo(() => sortMine(data ?? [], marks), [data, marks])
  const active = useMemo(() => new Set((data ?? []).map((task) => task.request_number)), [data])
  // Окончательные отказы, которые не покажет плитка заявки: «закрыта» / «не
  // ваша» — всегда; «переснять» — если заявки уже нет в списке.
  const lost = useMemo(
    () =>
      data
        ? queued.filter((i) => i.failed && (i.failed !== 'bad_photo' || !active.has(i.requestNumber)))
        : [],
    [queued, data, active],
  )

  let content
  // Есть кэш — показываем его даже при ошибке/без сети: список важнее.
  if (data) {
    content = tasks.length === 0 && lost.length === 0 ? (
      <div className="flex flex-col items-center gap-4 py-16 text-center">
        <PartyPopper size={72} className="text-emerald-500" aria-hidden />
        <p className="text-[24px] font-bold">{t('twa.simple.mine.empty')}</p>
      </div>
    ) : (
      <ul className="flex flex-col gap-3">
        {lost.map((item) => (
          <LostTile key={item.id} item={item} onDismiss={() => void dismiss(item.id)} />
        ))}
        {tasks.map((task) => {
          const state = tileState(task, marks)
          const path = `/twa/s/task/${encodeURIComponent(task.request_number)}`
          return (
            <TaskTile
              key={task.request_number}
              requestNumber={task.request_number}
              category={task.category}
              address={task.address?.trim() || tCategory(task.category, t)}
              text={firstLine(task.description)}
              urgency={task.urgency}
              state={state}
              reason={returnReason(task)}
              onOpen={() => navigate(state === 'retake' ? `${path}/done` : path)}
            />
          )
        })}
      </ul>
    )
  } else if (isError) {
    content = <ErrorBlock onRetry={() => void refetch()} />
  } else if (isLoading) {
    content = <Loading />
  } else {
    // Запрос на паузе без сети и без кэша: не «пусто», а ошибка с повтором.
    content = <ErrorBlock onRetry={() => void refetch()} />
  }

  return (
    <>
      <main className="p-3 pb-[160px]">{content}</main>
      <SimpleTabs />
    </>
  )
}
