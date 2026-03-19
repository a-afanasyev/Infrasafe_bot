import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { apiClient } from '../../api/client'
import type { EmployeeBrief } from '../../hooks/useEmployees'
import type { KanbanColumn, RequestCard } from '../../hooks/useKanban'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { cn } from '@/lib/utils'

const ASSIGNABLE_STATUSES = new Set(['Новая', 'В работе'])

interface Props {
  employee: EmployeeBrief
  onClose: () => void
}

export default function AssignRequestModal({ employee, onClose }: Props) {
  const queryClient = useQueryClient()
  const [assignError, setAssignError] = useState<string | null>(null)

  const { data, isLoading } = useQuery<{ columns: KanbanColumn[] }>({
    queryKey: ['kanban', {}],
    queryFn: () => apiClient.get('/api/v2/requests/kanban').then(r => r.data),
    staleTime: 30_000,
  })

  // Column order from API response determines display order (typically 'Новая' before 'В работе')
  const requests: RequestCard[] = (data?.columns ?? [])
    .filter(col => ASSIGNABLE_STATUSES.has(col.status))
    .flatMap(col => col.requests)

  const assignMutation = useMutation({
    mutationFn: (requestNumber: string) =>
      apiClient
        .patch(`/api/v2/requests/${requestNumber}`, { executor_id: employee.id })
        .then(r => r.data),
    onSuccess: () => {
      toast.success('Исполнитель назначен')
      queryClient.invalidateQueries({ queryKey: ['kanban'] })
      queryClient.invalidateQueries({ queryKey: ['employees'] })
      onClose()
    },
    onError: () => {
      toast.error('Не удалось назначить заявку')
      setAssignError('Не удалось назначить заявку. Попробуйте снова.')
    },
  })

  const employeeName =
    [employee.first_name, employee.last_name].filter(Boolean).join(' ') || 'Сотрудник'

  return (
    <Dialog open onOpenChange={(open) => { if (!open) onClose() }}>
      <DialogContent className="max-w-[480px] max-h-[80vh] flex flex-col overflow-hidden p-0">
        <DialogHeader className="p-5 px-6 pb-4 border-b border-border-default">
          <DialogTitle>Назначить заявку</DialogTitle>
          <p className="text-[13px] text-text-muted mt-0.5">{employeeName}</p>
        </DialogHeader>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-3 px-4">
          {isLoading ? (
            <div className="text-center py-10 text-text-muted text-sm">
              Загрузка заявок...
            </div>
          ) : requests.length === 0 ? (
            <div className="text-center py-10 text-text-muted text-sm">
              Нет заявок для назначения
            </div>
          ) : (
            <div className="flex flex-col gap-1.5">
              {requests.map(req => (
                <RequestRow
                  key={req.request_number}
                  request={req}
                  isPending={assignMutation.isPending}
                  onSelect={() => assignMutation.mutate(req.request_number)}
                />
              ))}
            </div>
          )}
          {assignError && (
            <p className="text-sm text-red mt-2">{assignError}</p>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}

interface RowProps {
  request: RequestCard
  isPending: boolean
  onSelect: () => void
}

function RequestRow({ request, isPending, onSelect }: RowProps) {
  return (
    <button
      disabled={isPending}
      onClick={onSelect}
      className={cn(
        'flex flex-col items-start gap-1 w-full text-left bg-transparent border border-border-default rounded-lg p-3 px-3.5 transition-colors',
        isPending ? 'cursor-not-allowed opacity-60' : 'cursor-pointer hover:bg-bg-surface hover:border-border-active'
      )}
    >
      <div className="flex items-center gap-2.5 w-full">
        <span className="font-[family-name:var(--font-mono)] text-xs text-text-muted shrink-0">
          #{request.request_number}
        </span>
        <span className="font-bold text-[13px] text-text-primary truncate">
          {request.category}
        </span>
        <span className="ml-auto text-[11px] font-semibold px-2 py-0.5 rounded-[10px] bg-blue/[.12] text-blue shrink-0">
          Назначить
        </span>
      </div>
      {(request.description) && (
        <span className="text-xs text-text-muted truncate max-w-full">
          {request.description}
        </span>
      )}
    </button>
  )
}
