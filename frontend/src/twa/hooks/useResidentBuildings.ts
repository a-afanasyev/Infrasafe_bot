import { useQuery } from '@tanstack/react-query'
import { twaClient } from '../twaClient'

interface AddressItem {
  id: number
  label: string
  building_id?: number
}

/** Дома жителя: из квартир (building_id) и привязок к домам. */
export function useResidentBuildings() {
  return useQuery<AddressItem[]>({
    queryKey: ['twa', 'cleaning', 'my-buildings'],
    queryFn: async () => {
      const { data } = await twaClient.get('/api/v2/profile/request-addresses')
      const byId = new Map<number, AddressItem>()
      for (const building of (data.buildings ?? []) as AddressItem[]) byId.set(building.id, building)
      for (const flat of (data.apartments ?? []) as AddressItem[]) {
        if (flat.building_id && !byId.has(flat.building_id)) byId.set(flat.building_id, { id: flat.building_id, label: flat.label })
      }
      return [...byId.values()]
    },
    staleTime: 60_000,
  })
}
