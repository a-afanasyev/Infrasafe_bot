import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { twaClient } from '../../twaClient'
import RequestCard from '../../components/RequestCard'
import { Star } from 'lucide-react'

export default function ArchivePage() {
  const { t } = useTranslation()

  const { data: requests = [], isLoading } = useQuery({
    queryKey: ['executor-tasks'],
    queryFn: () => twaClient.get('/api/v2/requests', {
      params: { scope: 'my', limit: 50 }
    }).then(r => r.data),
    staleTime: 30_000,
  })

  const archiveStatuses = ['Выполнена', 'Исполнено', 'Принято', 'Отменена']
  const archive = requests.filter((r: any) => archiveStatuses.includes(r.status))

  const completedCount = archive.filter((r: any) => ['Выполнена', 'Исполнено', 'Принято'].includes(r.status)).length

  return (
    <div className="p-4 pb-20 min-h-screen bg-gray-50 dark:bg-gray-950">
      <h1 className="text-lg font-bold text-gray-900 dark:text-gray-100 mb-4">{t('twa.exec.archive.title')}</h1>

      <div className="bg-white dark:bg-gray-800 rounded-2xl p-4 border border-gray-100 dark:border-gray-700 mb-4 flex items-center gap-4">
        <div className="flex items-center gap-2">
          <Star size={16} className="text-amber-400 fill-amber-400" />
          <span className="text-[13px] text-gray-600 dark:text-gray-400">{t('twa.exec.archive.completed')}: {completedCount}</span>
        </div>
      </div>

      {isLoading && <p className="text-center text-gray-400 py-8">{t('common.loading')}</p>}

      {!isLoading && archive.length === 0 && (
        <div className="text-center py-12">
          <p className="text-gray-400 text-[14px]">{t('twa.exec.archive.empty')}</p>
        </div>
      )}

      {archive.map((req: any) => (
        <RequestCard
          key={req.request_number}
          requestNumber={req.request_number}
          status={req.status}
          category={req.category}
          description={req.description}
          createdAt={req.created_at}
        />
      ))}
    </div>
  )
}
