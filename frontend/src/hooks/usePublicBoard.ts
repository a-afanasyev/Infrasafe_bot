import { useQuery } from '@tanstack/react-query'
import { publicClient } from '../api/publicClient'

// Anonymized request row — no number, no description, no personal data.
export interface PublicBoardRequest {
  category: string
  status: string
  created_at: string
}

export interface PublicBoardData {
  status_counts: Record<string, number>
  active_requests: PublicBoardRequest[]
  active_executors: number
  avg_resolution_hours: number | null
  avg_efficiency: number | null
}

// Public board data via polling — no WebSocket, no auth.
export function usePublicBoard() {
  return useQuery<PublicBoardData>({
    queryKey: ['public-board'],
    queryFn: () => publicClient.get('/api/v2/public/board').then((r) => r.data),
    refetchInterval: 45_000,
    staleTime: 30_000,
  })
}
