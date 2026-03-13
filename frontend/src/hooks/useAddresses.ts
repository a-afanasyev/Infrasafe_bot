import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiClient } from '../api/client'
import type {
  AddressStats,
  YardBrief,
  BuildingBrief,
  ApartmentBrief,
  ApartmentDetail,
  ModerationItem,
  BulkCreateResult,
} from '../types/api'

// ── Queries ──────────────────────────────────────────────────────────

export function useAddressStats() {
  return useQuery<AddressStats>({
    queryKey: ['address-stats'],
    queryFn: () => apiClient.get('/api/v2/addresses/stats').then(r => r.data),
    staleTime: 30_000,
  })
}

export function useYards(includeInactive?: boolean) {
  return useQuery<YardBrief[]>({
    queryKey: ['yards', includeInactive],
    queryFn: () =>
      apiClient
        .get('/api/v2/addresses/yards', {
          params: { include_inactive: includeInactive },
        })
        .then(r => r.data),
    staleTime: 30_000,
  })
}

export function useBuildings(yardId: number | null, includeInactive?: boolean) {
  return useQuery<BuildingBrief[]>({
    queryKey: ['buildings', yardId, includeInactive],
    queryFn: () =>
      apiClient
        .get(`/api/v2/addresses/yards/${yardId}/buildings`, {
          params: { include_inactive: includeInactive },
        })
        .then(r => r.data),
    enabled: yardId !== null,
    staleTime: 30_000,
  })
}

export function useApartments(buildingId: number | null, includeInactive?: boolean) {
  return useQuery<ApartmentBrief[]>({
    queryKey: ['apartments', buildingId, includeInactive],
    queryFn: () =>
      apiClient
        .get(`/api/v2/addresses/buildings/${buildingId}/apartments`, {
          params: { include_inactive: includeInactive },
        })
        .then(r => r.data),
    enabled: buildingId !== null,
    staleTime: 30_000,
  })
}

export function useSearchApartments(query: string) {
  return useQuery<ApartmentBrief[]>({
    queryKey: ['apartments', 'search', query],
    queryFn: () =>
      apiClient
        .get('/api/v2/addresses/apartments/search', {
          params: { q: query },
        })
        .then(r => r.data),
    enabled: query.length >= 2,
    staleTime: 30_000,
  })
}

export function useApartmentDetail(apartmentId: number | null) {
  return useQuery<ApartmentDetail>({
    queryKey: ['apartment-detail', apartmentId],
    queryFn: () =>
      apiClient.get(`/api/v2/addresses/apartments/${apartmentId}`).then(r => r.data),
    enabled: apartmentId !== null,
    staleTime: 30_000,
  })
}

export function usePendingModeration() {
  return useQuery<ModerationItem[]>({
    queryKey: ['moderation'],
    queryFn: () => apiClient.get('/api/v2/addresses/moderation').then(r => r.data),
    staleTime: 30_000,
  })
}

// ── Mutations ────────────────────────────────────────────────────────

// Yards

export function useCreateYard() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: Omit<YardBrief, 'id' | 'created_at' | 'buildings_count'>) =>
      apiClient.post('/api/v2/addresses/yards', body).then(r => r.data),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['yards'] }),
    onError: (error) => console.error('Create yard failed:', error),
  })
}

export function useUpdateYard() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...body }: { id: number } & Partial<YardBrief>) =>
      apiClient.patch(`/api/v2/addresses/yards/${id}`, body).then(r => r.data),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['yards'] }),
    onError: (error) => console.error('Update yard failed:', error),
  })
}

export function useDeleteYard() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) =>
      apiClient.delete(`/api/v2/addresses/yards/${id}`).then(r => r.data),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['yards'] }),
    onError: (error) => console.error('Delete yard failed:', error),
  })
}

// Buildings

export function useCreateBuilding() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: Omit<BuildingBrief, 'id' | 'created_at' | 'apartments_count' | 'yard_name'>) =>
      apiClient.post('/api/v2/addresses/buildings', body).then(r => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['buildings'] })
      queryClient.invalidateQueries({ queryKey: ['yards'] })
    },
    onError: (error) => console.error('Create building failed:', error),
  })
}

export function useUpdateBuilding() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...body }: { id: number } & Partial<BuildingBrief>) =>
      apiClient.patch(`/api/v2/addresses/buildings/${id}`, body).then(r => r.data),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['buildings'] }),
    onError: (error) => console.error('Update building failed:', error),
  })
}

export function useDeleteBuilding() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) =>
      apiClient.delete(`/api/v2/addresses/buildings/${id}`).then(r => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['buildings'] })
      queryClient.invalidateQueries({ queryKey: ['yards'] })
    },
    onError: (error) => console.error('Delete building failed:', error),
  })
}

// Apartments

export function useCreateApartment() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: Omit<ApartmentBrief, 'id' | 'created_at' | 'residents_count' | 'building_address' | 'yard_name'>) =>
      apiClient.post('/api/v2/addresses/apartments', body).then(r => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['apartments'] })
      queryClient.invalidateQueries({ queryKey: ['buildings'] })
    },
    onError: (error) => console.error('Create apartment failed:', error),
  })
}

export function useUpdateApartment() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...body }: { id: number } & Partial<ApartmentBrief>) =>
      apiClient.patch(`/api/v2/addresses/apartments/${id}`, body).then(r => r.data),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['apartments'] }),
    onError: (error) => console.error('Update apartment failed:', error),
  })
}

export function useDeleteApartment() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) =>
      apiClient.delete(`/api/v2/addresses/apartments/${id}`).then(r => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['apartments'] })
      queryClient.invalidateQueries({ queryKey: ['buildings'] })
    },
    onError: (error) => console.error('Delete apartment failed:', error),
  })
}

export function useBulkCreateApartments() {
  const queryClient = useQueryClient()
  return useMutation<BulkCreateResult, Error, { building_id: number; apartment_numbers: string[] }>({
    mutationFn: (body) =>
      apiClient.post('/api/v2/addresses/apartments/bulk', body).then(r => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['apartments'] })
      queryClient.invalidateQueries({ queryKey: ['buildings'] })
    },
    onError: (error) => console.error('Bulk create apartments failed:', error),
  })
}

// Moderation

export function useApproveModeration() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) =>
      apiClient.post(`/api/v2/addresses/moderation/${id}/approve`).then(r => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['moderation'] })
      queryClient.invalidateQueries({ queryKey: ['address-stats'] })
    },
    onError: (error) => console.error('Approve moderation failed:', error),
  })
}

export function useRejectModeration() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, comment }: { id: number; comment: string }) =>
      apiClient.post(`/api/v2/addresses/moderation/${id}/reject`, { comment }).then(r => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['moderation'] })
      queryClient.invalidateQueries({ queryKey: ['address-stats'] })
    },
    onError: (error) => console.error('Reject moderation failed:', error),
  })
}
