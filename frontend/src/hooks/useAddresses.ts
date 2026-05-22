import { useCallback } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import i18n from '../i18n'
import { apiClient } from '../api/client'
import { useWebSocket } from './useWebSocket'
import { safeErrorMessage } from '@/utils/errorMessage'
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

export function useAllBuildings(yardId?: number | null, includeInactive?: boolean) {
  return useQuery<BuildingBrief[]>({
    queryKey: ['all-buildings', yardId, includeInactive],
    queryFn: () =>
      apiClient
        .get('/api/v2/addresses/buildings', {
          params: {
            ...(yardId ? { yard_id: yardId } : {}),
            include_inactive: includeInactive,
          },
        })
        .then(r => r.data),
    staleTime: 30_000,
  })
}

export function useAllApartments(yardId?: number | null, buildingId?: number | null, includeInactive?: boolean) {
  return useQuery<ApartmentBrief[]>({
    queryKey: ['all-apartments', yardId, buildingId, includeInactive],
    queryFn: () =>
      apiClient
        .get('/api/v2/addresses/apartments/all', {
          params: {
            ...(yardId ? { yard_id: yardId } : {}),
            ...(buildingId ? { building_id: buildingId } : {}),
            include_inactive: includeInactive,
          },
        })
        .then(r => r.data),
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
    onSuccess: () => {
      toast.success(i18n.t('toast.yardCreated'))
      queryClient.invalidateQueries({ queryKey: ['yards'] })
    },
    onError: (error: Error) => {
      console.error('Create yard failed:', error)
      toast.error(i18n.t('toast.yardCreateFailed'), { description: safeErrorMessage(error, 'An error occurred') })
    },
  })
}

export function useUpdateYard() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...body }: { id: number } & Partial<YardBrief>) =>
      apiClient.patch(`/api/v2/addresses/yards/${id}`, body).then(r => r.data),
    onSuccess: () => {
      toast.success(i18n.t('toast.yardUpdated'))
      queryClient.invalidateQueries({ queryKey: ['yards'] })
    },
    onError: (error: Error) => {
      console.error('Update yard failed:', error)
      toast.error(i18n.t('toast.yardUpdateFailed'), { description: safeErrorMessage(error, 'An error occurred') })
    },
  })
}

export function useDeleteYard() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) =>
      apiClient.delete(`/api/v2/addresses/yards/${id}`).then(r => r.data),
    onSuccess: () => {
      toast.success(i18n.t('toast.yardDeleted'))
      queryClient.invalidateQueries({ queryKey: ['yards'] })
    },
    onError: (error: Error) => {
      console.error('Delete yard failed:', error)
      toast.error(i18n.t('toast.yardDeleteFailed'), { description: safeErrorMessage(error, 'An error occurred') })
    },
  })
}

/** Hard-delete a soft-deleted yard. Cascades to inactive buildings → apartments. */
export function usePurgeYard() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) =>
      apiClient.delete(`/api/v2/addresses/yards/${id}/purge`).then(r => r.data),
    onSuccess: () => {
      toast.success(i18n.t('toast.yardPurged'))
      queryClient.invalidateQueries({ queryKey: ['yards'] })
      queryClient.invalidateQueries({ queryKey: ['buildings'] })
      queryClient.invalidateQueries({ queryKey: ['address-stats'] })
    },
    onError: (error: Error) => {
      console.error('Purge yard failed:', error)
      toast.error(i18n.t('toast.yardPurgeFailed'), { description: safeErrorMessage(error, 'An error occurred') })
    },
  })
}

// Buildings

export function useCreateBuilding() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: Omit<BuildingBrief, 'id' | 'created_at' | 'apartments_count' | 'yard_name'>) =>
      apiClient.post('/api/v2/addresses/buildings', body).then(r => r.data),
    onSuccess: () => {
      toast.success(i18n.t('toast.buildingCreated'))
      queryClient.invalidateQueries({ queryKey: ['buildings'] })
      queryClient.invalidateQueries({ queryKey: ['yards'] })
    },
    onError: (error: Error) => {
      console.error('Create building failed:', error)
      toast.error(i18n.t('toast.buildingCreateFailed'), { description: safeErrorMessage(error, 'An error occurred') })
    },
  })
}

export function useUpdateBuilding() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...body }: { id: number } & Partial<BuildingBrief>) =>
      apiClient.patch(`/api/v2/addresses/buildings/${id}`, body).then(r => r.data),
    onSuccess: () => {
      toast.success(i18n.t('toast.buildingUpdated'))
      queryClient.invalidateQueries({ queryKey: ['buildings'] })
    },
    onError: (error: Error) => {
      console.error('Update building failed:', error)
      toast.error(i18n.t('toast.buildingUpdateFailed'), { description: safeErrorMessage(error, 'An error occurred') })
    },
  })
}

export function useDeleteBuilding() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) =>
      apiClient.delete(`/api/v2/addresses/buildings/${id}`).then(r => r.data),
    onSuccess: () => {
      toast.success(i18n.t('toast.buildingDeleted'))
      queryClient.invalidateQueries({ queryKey: ['buildings'] })
      queryClient.invalidateQueries({ queryKey: ['yards'] })
    },
    onError: (error: Error) => {
      console.error('Delete building failed:', error)
      toast.error(i18n.t('toast.buildingDeleteFailed'), { description: safeErrorMessage(error, 'An error occurred') })
    },
  })
}

/** Hard-delete a building that has already been soft-deleted. */
export function usePurgeBuilding() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) =>
      apiClient.delete(`/api/v2/addresses/buildings/${id}/purge`).then(r => r.data),
    onSuccess: () => {
      toast.success(i18n.t('toast.buildingPurged'))
      queryClient.invalidateQueries({ queryKey: ['buildings'] })
      queryClient.invalidateQueries({ queryKey: ['yards'] })
      queryClient.invalidateQueries({ queryKey: ['address-stats'] })
    },
    onError: (error: Error) => {
      console.error('Purge building failed:', error)
      toast.error(i18n.t('toast.buildingPurgeFailed'), { description: safeErrorMessage(error, 'An error occurred') })
    },
  })
}

// Apartments

export function useCreateApartment() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: Omit<ApartmentBrief, 'id' | 'created_at' | 'residents_count' | 'building_address' | 'yard_name'>) =>
      apiClient.post('/api/v2/addresses/apartments', body).then(r => r.data),
    onSuccess: () => {
      toast.success(i18n.t('toast.apartmentCreated'))
      queryClient.invalidateQueries({ queryKey: ['apartments'] })
      queryClient.invalidateQueries({ queryKey: ['buildings'] })
    },
    onError: (error: Error) => {
      console.error('Create apartment failed:', error)
      toast.error(i18n.t('toast.apartmentCreateFailed'), { description: safeErrorMessage(error, 'An error occurred') })
    },
  })
}

export function useUpdateApartment() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...body }: { id: number } & Partial<ApartmentBrief>) =>
      apiClient.patch(`/api/v2/addresses/apartments/${id}`, body).then(r => r.data),
    onSuccess: () => {
      toast.success(i18n.t('toast.apartmentUpdated'))
      queryClient.invalidateQueries({ queryKey: ['apartments'] })
    },
    onError: (error: Error) => {
      console.error('Update apartment failed:', error)
      toast.error(i18n.t('toast.apartmentUpdateFailed'), { description: safeErrorMessage(error, 'An error occurred') })
    },
  })
}

export function useDeleteApartment() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) =>
      apiClient.delete(`/api/v2/addresses/apartments/${id}`).then(r => r.data),
    onSuccess: () => {
      toast.success(i18n.t('toast.apartmentDeleted'))
      queryClient.invalidateQueries({ queryKey: ['apartments'] })
      queryClient.invalidateQueries({ queryKey: ['buildings'] })
    },
    onError: (error: Error) => {
      console.error('Delete apartment failed:', error)
      toast.error(i18n.t('toast.apartmentDeleteFailed'), { description: safeErrorMessage(error, 'An error occurred') })
    },
  })
}

/** Hard-delete a soft-deleted apartment. Refuses on linked requests / approved residents. */
export function usePurgeApartment() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) =>
      apiClient.delete(`/api/v2/addresses/apartments/${id}/purge`).then(r => r.data),
    onSuccess: () => {
      toast.success(i18n.t('toast.apartmentPurged'))
      queryClient.invalidateQueries({ queryKey: ['apartments'] })
      queryClient.invalidateQueries({ queryKey: ['buildings'] })
      queryClient.invalidateQueries({ queryKey: ['address-stats'] })
    },
    onError: (error: Error) => {
      console.error('Purge apartment failed:', error)
      toast.error(i18n.t('toast.apartmentPurgeFailed'), { description: safeErrorMessage(error, 'An error occurred') })
    },
  })
}

export function useBulkCreateApartments() {
  const queryClient = useQueryClient()
  return useMutation<BulkCreateResult, Error, { building_id: number; apartment_numbers: string[] }>({
    mutationFn: (body) =>
      apiClient.post('/api/v2/addresses/apartments/bulk', body).then(r => r.data),
    onSuccess: () => {
      toast.success(i18n.t('toast.bulkCreated'))
      queryClient.invalidateQueries({ queryKey: ['apartments'] })
      queryClient.invalidateQueries({ queryKey: ['buildings'] })
    },
    onError: (error: Error) => {
      console.error('Bulk create apartments failed:', error)
      toast.error(i18n.t('toast.bulkCreateFailed'), { description: safeErrorMessage(error, 'An error occurred') })
    },
  })
}

// Moderation

export function useApproveModeration() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) =>
      apiClient.post(`/api/v2/addresses/moderation/${id}/approve`).then(r => r.data),
    onSuccess: () => {
      toast.success(i18n.t('toast.addressApproved'))
      queryClient.invalidateQueries({ queryKey: ['moderation'] })
      queryClient.invalidateQueries({ queryKey: ['address-stats'] })
    },
    onError: (error: Error) => {
      console.error('Approve moderation failed:', error)
      toast.error(i18n.t('toast.addressApproveFailed'), { description: safeErrorMessage(error, 'An error occurred') })
    },
  })
}

export function useRejectModeration() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, comment }: { id: number; comment: string }) =>
      apiClient.post(`/api/v2/addresses/moderation/${id}/reject`, { comment }).then(r => r.data),
    onSuccess: () => {
      toast.success(i18n.t('toast.addressRejected'))
      queryClient.invalidateQueries({ queryKey: ['moderation'] })
      queryClient.invalidateQueries({ queryKey: ['address-stats'] })
    },
    onError: (error: Error) => {
      console.error('Reject moderation failed:', error)
      toast.error(i18n.t('toast.addressRejectFailed'), { description: safeErrorMessage(error, 'An error occurred') })
    },
  })
}

// ── Real-time ────────────────────────────────────────────────────────

/** Subscribe to the /ws/v2/buildings channel and refresh address queries on
 *  building.* events emitted by the bot or the API (ARCH-014). */
export function useAddressesWebSocket() {
  const queryClient = useQueryClient()
  const onEvent = useCallback((event: { type: string; data: unknown }) => {
    if (typeof event.type === 'string' && event.type.startsWith('building.')) {
      queryClient.invalidateQueries({ queryKey: ['buildings'] })
      queryClient.invalidateQueries({ queryKey: ['all-buildings'] })
      queryClient.invalidateQueries({ queryKey: ['yards'] })
      queryClient.invalidateQueries({ queryKey: ['address-stats'] })
    }
  }, [queryClient])
  useWebSocket('buildings', onEvent)
}
