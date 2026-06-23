import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { twaClient } from '../twaClient'

/** Executor-facing transfer (TWA PR-T1 endpoint `/executor/shifts/transfers`). */
export interface TwaTransfer {
  id: number
  shift_id: number
  status: string
  reason: string
  urgency_level: string
  comment: string | null
  from_executor_id: number
  to_executor_id: number | null
  from_executor_name: string | null
  to_executor_name: string | null
  direction: 'outgoing' | 'incoming'
  can_respond: boolean
  shift_start_time: string | null
  created_at: string | null
}

export interface InitiateTransferInput {
  shift_id: number
  reason: string
  comment?: string
  urgency_level?: string
}

const TRANSFERS = '/api/v2/executor/shifts/transfers'

export function useMyTransfers() {
  return useQuery<TwaTransfer[]>({
    queryKey: ['twa', 'my-transfers'],
    queryFn: () => twaClient.get(TRANSFERS).then(r => r.data),
    staleTime: 30_000,
  })
}

export function useInitiateTransfer() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: InitiateTransferInput) =>
      twaClient.post(TRANSFERS, body).then(r => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['twa', 'my-transfers'] })
      queryClient.invalidateQueries({ queryKey: ['twa', 'my-shifts'] })
    },
  })
}

export function useRespondTransfer() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, action }: { id: number; action: 'accept' | 'reject' }) =>
      twaClient.post(`${TRANSFERS}/${id}/respond`, { action }).then(r => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['twa', 'my-transfers'] })
      queryClient.invalidateQueries({ queryKey: ['twa', 'my-shifts'] })
      queryClient.invalidateQueries({ queryKey: ['twa', 'current-shift'] })
    },
  })
}
