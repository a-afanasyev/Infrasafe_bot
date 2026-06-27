import { describe, it, expect, vi } from 'vitest'
import type { ReactNode } from 'react'
import { createElement } from 'react'
import { http, HttpResponse } from 'msw'
import { waitFor, renderHook } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { I18nextProvider } from 'react-i18next'
import { toast } from 'sonner'
import { testI18n } from '@/test/test-utils'
import { server } from '@/test/msw/server'
import {
  useAccessZones,
  useCreateZone,
  useUpdateZone,
  useUpdateZoneYards,
  useCreateGate,
  useCreateCamera,
  useCreateBarrier,
  useCreateController,
  useRotateControllerKey,
} from './useAccessEquipment'

// Тосты мутаций мокаем (как в useAccessRegistry.test) — проверяем текст i18n.
vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}))

function makeClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  })
}
function wrapperFor(qc: QueryClient) {
  return ({ children }: { children: ReactNode }) =>
    createElement(
      QueryClientProvider,
      { client: qc },
      createElement(I18nextProvider, { i18n: testI18n }, children),
    )
}

describe('useAccessZones', () => {
  it('GET /admin/zones → конверт {items,total,...}', async () => {
    let seenUrl = ''
    server.use(
      http.get('*/api/v1/access/admin/zones', ({ request }) => {
        seenUrl = request.url
        return HttpResponse.json({
          items: [{ id: 1, code: 'Z1', name: 'Зона 1', offline_mode: 'fail_closed', is_active: true }],
          total: 1,
          limit: 50,
          offset: 0,
        })
      }),
    )
    const qc = makeClient()
    const { result } = renderHook(() => useAccessZones(), { wrapper: wrapperFor(qc) })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(seenUrl).toContain('/admin/zones')
    expect(result.current.data?.items[0].code).toBe('Z1')
  })
})

describe('useCreateZone', () => {
  it('POST /admin/zones + инвалидирует access-zones + toast', async () => {
    let body: unknown = null
    server.use(
      http.post('*/api/v1/access/admin/zones', async ({ request }) => {
        body = await request.json()
        return HttpResponse.json({ id: 2, code: 'Z2', name: 'Зона 2', offline_mode: 'fail_closed', is_active: true }, { status: 201 })
      }),
    )
    const qc = makeClient()
    const spy = vi.spyOn(qc, 'invalidateQueries')
    const { result } = renderHook(() => useCreateZone(), { wrapper: wrapperFor(qc) })
    result.current.mutate({ code: 'Z2', name: 'Зона 2', offline_mode: 'fail_closed' })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(body).toMatchObject({ code: 'Z2', name: 'Зона 2', offline_mode: 'fail_closed' })
    expect(spy).toHaveBeenCalledWith({ queryKey: ['access-zones'] })
    expect(toast.success).toHaveBeenCalledWith('Зона создана')
  })

  it('409 → toast «уже существует»', async () => {
    server.use(
      http.post('*/api/v1/access/admin/zones', () =>
        HttpResponse.json({ detail: 'duplicate' }, { status: 409 }),
      ),
    )
    const qc = makeClient()
    const { result } = renderHook(() => useCreateZone(), { wrapper: wrapperFor(qc) })
    result.current.mutate({ code: 'Z2', name: 'x', offline_mode: 'fail_closed' })
    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(toast.error).toHaveBeenCalledWith('Такой элемент уже существует')
  })
})

describe('useUpdateZone', () => {
  it('PATCH /admin/zones/{id} + инвалидирует + toast', async () => {
    let body: unknown = null
    server.use(
      http.patch('*/api/v1/access/admin/zones/5', async ({ request }) => {
        body = await request.json()
        return HttpResponse.json({ id: 5, code: 'Z5', name: 'Зона 5', offline_mode: 'fail_closed', is_active: false })
      }),
    )
    const qc = makeClient()
    const spy = vi.spyOn(qc, 'invalidateQueries')
    const { result } = renderHook(() => useUpdateZone(), { wrapper: wrapperFor(qc) })
    result.current.mutate({ id: 5, payload: { code: 'Z5', name: 'Зона 5', offline_mode: 'fail_closed', is_active: false } })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(body).toMatchObject({ is_active: false })
    expect(spy).toHaveBeenCalledWith({ queryKey: ['access-zones'] })
    expect(toast.success).toHaveBeenCalledWith('Изменения сохранены')
  })
})

describe('useUpdateZoneYards', () => {
  it('POST /admin/zones/{id}/yards с add/remove + инвалидирует zones', async () => {
    let body: unknown = null
    server.use(
      http.post('*/api/v1/access/admin/zones/5/yards', async ({ request }) => {
        body = await request.json()
        return HttpResponse.json({ zone_id: 5, yard_ids: [10] })
      }),
    )
    const qc = makeClient()
    const spy = vi.spyOn(qc, 'invalidateQueries')
    const { result } = renderHook(() => useUpdateZoneYards(), { wrapper: wrapperFor(qc) })
    result.current.mutate({ id: 5, payload: { add: [10] } })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(body).toMatchObject({ add: [10] })
    expect(spy).toHaveBeenCalledWith({ queryKey: ['access-zones'] })
  })
})

describe('useCreateGate', () => {
  it('POST /admin/gates с zone_id/direction + инвалидирует access-gates', async () => {
    let body: unknown = null
    server.use(
      http.post('*/api/v1/access/admin/gates', async ({ request }) => {
        body = await request.json()
        return HttpResponse.json({ id: 1, code: 'G1', zone_id: 5, direction: 'entry', is_active: true }, { status: 201 })
      }),
    )
    const qc = makeClient()
    const spy = vi.spyOn(qc, 'invalidateQueries')
    const { result } = renderHook(() => useCreateGate(), { wrapper: wrapperFor(qc) })
    result.current.mutate({ code: 'G1', zone_id: 5, direction: 'entry' })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(body).toMatchObject({ code: 'G1', zone_id: 5, direction: 'entry' })
    expect(spy).toHaveBeenCalledWith({ queryKey: ['access-gates'] })
    expect(toast.success).toHaveBeenCalledWith('Въезд создан')
  })
})

describe('useCreateCamera', () => {
  it('POST /admin/cameras + инвалидирует access-cameras', async () => {
    server.use(
      http.post('*/api/v1/access/admin/cameras', () =>
        HttpResponse.json({ id: 1, code: 'C1', gate_id: 1, direction: 'entry', is_active: true }, { status: 201 }),
      ),
    )
    const qc = makeClient()
    const spy = vi.spyOn(qc, 'invalidateQueries')
    const { result } = renderHook(() => useCreateCamera(), { wrapper: wrapperFor(qc) })
    result.current.mutate({ code: 'C1', gate_id: 1, direction: 'entry' })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(spy).toHaveBeenCalledWith({ queryKey: ['access-cameras'] })
    expect(toast.success).toHaveBeenCalledWith('Камера добавлена')
  })
})

describe('useCreateBarrier', () => {
  it('POST /admin/barriers + инвалидирует access-barriers', async () => {
    server.use(
      http.post('*/api/v1/access/admin/barriers', () =>
        HttpResponse.json({ id: 1, code: 'B1', gate_id: 1, is_active: true }, { status: 201 }),
      ),
    )
    const qc = makeClient()
    const spy = vi.spyOn(qc, 'invalidateQueries')
    const { result } = renderHook(() => useCreateBarrier(), { wrapper: wrapperFor(qc) })
    result.current.mutate({ code: 'B1', gate_id: 1 })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(spy).toHaveBeenCalledWith({ queryKey: ['access-barriers'] })
    expect(toast.success).toHaveBeenCalledWith('Шлагбаум добавлен')
  })
})

describe('useCreateController', () => {
  it('POST /admin/controllers → ответ содержит api_key (один раз)', async () => {
    let body: unknown = null
    server.use(
      http.post('*/api/v1/access/admin/controllers', async ({ request }) => {
        body = await request.json()
        return HttpResponse.json(
          {
            id: 1,
            controller_uid: 'ctrl-001',
            name: 'Контроллер 1',
            zone_id: 5,
            offline_mode: 'fail_closed',
            ip_allowlist: ['10.0.0.1'],
            status: 'online',
            is_active: true,
            api_key: 'SECRET-PLAINTEXT-KEY',
          },
          { status: 201 },
        )
      }),
    )
    const qc = makeClient()
    const spy = vi.spyOn(qc, 'invalidateQueries')
    const { result } = renderHook(() => useCreateController(), { wrapper: wrapperFor(qc) })
    result.current.mutate({ controller_uid: 'ctrl-001', zone_id: 5, ip_allowlist: ['10.0.0.1'] })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(body).toMatchObject({ controller_uid: 'ctrl-001', zone_id: 5, ip_allowlist: ['10.0.0.1'] })
    expect(result.current.data?.api_key).toBe('SECRET-PLAINTEXT-KEY')
    expect(spy).toHaveBeenCalledWith({ queryKey: ['access-controllers'] })
    expect(toast.success).toHaveBeenCalledWith('Контроллер создан')
  })
})

describe('useRotateControllerKey', () => {
  it('POST /admin/controllers/{id}/rotate-key → новый api_key', async () => {
    server.use(
      http.post('*/api/v1/access/admin/controllers/1/rotate-key', () =>
        HttpResponse.json({ controller_id: 1, controller_uid: 'ctrl-001', api_key: 'NEW-ROTATED-KEY' }),
      ),
    )
    const qc = makeClient()
    const spy = vi.spyOn(qc, 'invalidateQueries')
    const { result } = renderHook(() => useRotateControllerKey(), { wrapper: wrapperFor(qc) })
    result.current.mutate({ id: 1 })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data?.api_key).toBe('NEW-ROTATED-KEY')
    expect(spy).toHaveBeenCalledWith({ queryKey: ['access-controllers'] })
    expect(toast.success).toHaveBeenCalledWith('Ключ обновлён')
  })
})
