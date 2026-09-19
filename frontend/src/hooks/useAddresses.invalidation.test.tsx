import { describe, it, expect } from 'vitest'
import { http, HttpResponse } from 'msw'
import { waitFor } from '@testing-library/react'
import { renderHook } from '@/test/test-utils'
import { server } from '@/test/msw/server'
import {
  useAllApartments,
  useBulkCreateApartments,
  useCreateApartment,
  useDeleteApartment,
  usePurgeApartment,
  useUpdateApartment,
} from './useAddresses'

// AUD8-FE-01: плоский список «Все квартиры» (['all-apartments']) и пикер привязки
// жителя читают отдельный ключ, который ни одна мутация квартир не инвалидировала —
// после создания/правки/удаления до 30 с staleTime показывались старые данные.

const APT = { id: 1, number: '7', building_id: 12, floor: 1, is_active: true }

function useHarness() {
  return {
    all: useAllApartments(),
    create: useCreateApartment(),
    update: useUpdateApartment(),
    del: useDeleteApartment(),
    purge: usePurgeApartment(),
    bulk: useBulkCreateApartments(),
  }
}

function installHandlers() {
  let gets = 0
  server.use(
    http.get('*/api/v2/addresses/apartments/all', () => {
      gets += 1
      return HttpResponse.json([APT])
    }),
    http.post('*/api/v2/addresses/apartments', () => HttpResponse.json(APT, { status: 201 })),
    http.post('*/api/v2/addresses/apartments/bulk', () => HttpResponse.json({ created: 1 })),
    http.patch('*/api/v2/addresses/apartments/:id', () => HttpResponse.json(APT)),
    http.delete('*/api/v2/addresses/apartments/:id/purge', () => HttpResponse.json({ ok: true })),
    http.delete('*/api/v2/addresses/apartments/:id', () => HttpResponse.json({ ok: true })),
  )
  return () => gets
}

const CASES: Array<[string, (h: ReturnType<typeof useHarness>) => void]> = [
  ['create', (h) => h.create.mutate({ number: '8', building_id: 12, floor: 1, is_active: true } as never)],
  ['update', (h) => h.update.mutate({ id: 1, number: '9' })],
  ['delete', (h) => h.del.mutate(1)],
  ['purge', (h) => h.purge.mutate(1)],
  ['bulk', (h) => h.bulk.mutate({ building_id: 12, from: 1, to: 3 } as never)],
]

describe('мутации квартир инвалидируют all-apartments', () => {
  for (const [name, fire] of CASES) {
    it(`${name} → повторный GET /apartments/all`, async () => {
      const gets = installHandlers()
      const { result } = renderHook(useHarness)
      await waitFor(() => expect(result.current.all.isSuccess).toBe(true))
      expect(gets()).toBe(1)
      fire(result.current)
      await waitFor(() => expect(gets()).toBe(2))
    })
  }
})
