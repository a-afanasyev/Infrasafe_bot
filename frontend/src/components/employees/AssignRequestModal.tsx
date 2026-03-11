import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiClient } from '../../api/client'
import type { EmployeeBrief } from '../../hooks/useEmployees'
import type { KanbanColumn, RequestCard } from '../../hooks/useKanban'

const IN_WORK_STATUS = 'В работе' // matches API status value

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

  const inWorkColumn = data?.columns.find(col => col.status === IN_WORK_STATUS)
  const requests: RequestCard[] = inWorkColumn?.requests ?? []

  const assignMutation = useMutation({
    mutationFn: (requestNumber: string) =>
      apiClient
        .patch(`/api/v2/requests/${requestNumber}`, { executor_id: employee.id })
        .then(r => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['kanban'] })
      queryClient.invalidateQueries({ queryKey: ['employees'] })
      onClose()
    },
    onError: () => setAssignError('Не удалось назначить заявку. Попробуйте снова.'),
  })

  const employeeName =
    [employee.first_name, employee.last_name].filter(Boolean).join(' ') || 'Сотрудник'

  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(0,0,0,0.6)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 1000,
      }}
    >
      <div
        onClick={e => e.stopPropagation()}
        style={{
          background: '#fff',
          borderRadius: 12,
          width: '100%',
          maxWidth: 480,
          maxHeight: '80vh',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
          boxShadow: '0 24px 60px rgba(0,0,0,0.35)',
        }}
      >
        {/* Header */}
        <div
          style={{
            padding: '20px 24px 16px',
            borderBottom: '1px solid #e5e7eb',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <div>
            <div
              style={{
                fontWeight: 700,
                fontSize: '16px',
                color: '#111827',
                fontFamily: 'var(--font-display)',
              }}
            >
              Назначить заявку
            </div>
            <div style={{ fontSize: '13px', color: '#6b7280', marginTop: 2 }}>
              {employeeName}
            </div>
          </div>
          <button
            onClick={onClose}
            style={{
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              fontSize: '20px',
              color: '#9ca3af',
              lineHeight: 1,
              padding: '4px',
            }}
          >
            ×
          </button>
        </div>

        {/* Body */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '12px 16px' }}>
          {isLoading ? (
            <div
              style={{
                textAlign: 'center',
                padding: '40px 0',
                color: '#9ca3af',
                fontSize: '14px',
              }}
            >
              Загрузка заявок...
            </div>
          ) : requests.length === 0 ? (
            <div
              style={{
                textAlign: 'center',
                padding: '40px 0',
                color: '#9ca3af',
                fontSize: '14px',
              }}
            >
              Нет заявок в работе
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
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
            <p className="text-sm text-red-600 mt-2">{assignError}</p>
          )}
        </div>
      </div>
    </div>
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
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'flex-start',
        gap: '4px',
        width: '100%',
        textAlign: 'left',
        background: 'none',
        border: '1px solid #e5e7eb',
        borderRadius: 8,
        padding: '12px 14px',
        cursor: isPending ? 'not-allowed' : 'pointer',
        opacity: isPending ? 0.6 : 1,
        transition: 'background 0.15s, border-color 0.15s',
      }}
      onMouseEnter={e => {
        if (!isPending) {
          ;(e.currentTarget as HTMLButtonElement).style.background = '#f9fafb'
          ;(e.currentTarget as HTMLButtonElement).style.borderColor = '#d1d5db'
        }
      }}
      onMouseLeave={e => {
        ;(e.currentTarget as HTMLButtonElement).style.background = 'none'
        ;(e.currentTarget as HTMLButtonElement).style.borderColor = '#e5e7eb'
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px', width: '100%' }}>
        <span
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: '12px',
            color: '#6b7280',
            flexShrink: 0,
          }}
        >
          #{request.request_number}
        </span>
        <span
          style={{
            fontWeight: 700,
            fontSize: '13px',
            color: '#111827',
            whiteSpace: 'nowrap',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
          }}
        >
          {request.category}
        </span>
        <span
          style={{
            marginLeft: 'auto',
            fontSize: '11px',
            fontWeight: 600,
            padding: '2px 8px',
            borderRadius: 10,
            background: 'rgba(59,130,246,0.12)',
            color: '#3b82f6',
            flexShrink: 0,
          }}
        >
          Назначить
        </span>
      </div>
      {(request.description) && (
        <span
          style={{
            fontSize: '12px',
            color: '#9ca3af',
            whiteSpace: 'nowrap',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            maxWidth: '100%',
          }}
        >
          {request.description}
        </span>
      )}
    </button>
  )
}
