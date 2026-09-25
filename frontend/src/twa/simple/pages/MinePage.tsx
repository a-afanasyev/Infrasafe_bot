import { useMemo } from 'react'
import { useNavigate } from 'react-router'
import { useTranslation } from 'react-i18next'
import { PartyPopper } from 'lucide-react'
import { tCategory } from '../../../i18n/apiMaps'
import { useExecutorTasks } from '../../hooks/useExecutorTasks'
import TaskTile from '../components/TaskTile'
import { SimpleTabs } from '../components/Chrome'
import { ErrorBlock, Loading } from '../components/Ui'
import { firstLine, returnReason, sortMine, tileState } from '../model'
import { pendingNumbers } from '../queue/policy'
import { useCompletionQueue } from '../queue/CompletionQueue'

/** «Мои»: назначенные активные заявки — вернули → срочные → по времени. */
export default function MinePage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { data, isLoading, isError, refetch } = useExecutorTasks('active')
  const { items: queued } = useCompletionQueue()
  const pending = useMemo(() => pendingNumbers(queued), [queued])
  const tasks = useMemo(() => sortMine(data ?? [], pending), [data, pending])

  let content
  // Есть кэш — показываем его даже при ошибке/без сети: список важнее.
  if (data) {
    content = tasks.length === 0 ? (
      <div className="flex flex-col items-center gap-4 py-16 text-center">
        <PartyPopper size={72} className="text-emerald-500" aria-hidden />
        <p className="text-[24px] font-bold">{t('twa.simple.mine.empty')}</p>
      </div>
    ) : (
      <ul className="flex flex-col gap-3">
        {tasks.map((task) => (
          <TaskTile
            key={task.request_number}
            requestNumber={task.request_number}
            category={task.category}
            address={task.address?.trim() || tCategory(task.category, t)}
            text={firstLine(task.description)}
            urgency={task.urgency}
            state={tileState(task, pending)}
            reason={returnReason(task)}
            onOpen={() => navigate(`/twa/s/task/${encodeURIComponent(task.request_number)}`)}
          />
        ))}
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
