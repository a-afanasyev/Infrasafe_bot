import { useTranslation } from 'react-i18next'
import { Plus } from 'lucide-react'
import LoadingSpinner from '../../shared/LoadingSpinner'
import { Button } from '@/components/ui/button'

// ── Общая обёртка панели (кнопка «Добавить» + загрузка/ошибка) ────────────────
export default function PanelShell({
  canManage,
  addLabel,
  onAdd,
  isLoading,
  isError,
  children,
}: {
  canManage: boolean
  addLabel: string
  onAdd: () => void
  isLoading: boolean
  isError: boolean
  children: React.ReactNode
}) {
  const { t } = useTranslation()
  return (
    <div className="flex flex-col gap-4">
      {canManage && (
        <div className="flex justify-end">
          <Button onClick={onAdd} className="gap-1.5">
            <Plus size={16} />
            {addLabel}
          </Button>
        </div>
      )}
      {isLoading ? (
        <LoadingSpinner />
      ) : isError ? (
        <p className="text-[13px] text-red">{t('common.error')}</p>
      ) : (
        children
      )}
    </div>
  )
}
