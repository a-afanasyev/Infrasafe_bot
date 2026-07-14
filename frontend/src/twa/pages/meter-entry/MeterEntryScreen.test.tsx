import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

// initData и twaClient.post — управляемые извне (vi.hoisted, т.к. vi.mock хойстится).
const { initDataRef, postSpy } = vi.hoisted(() => ({
  initDataRef: { current: 'INIT' },
  postSpy: vi.fn(),
}))

vi.mock('@/utils/isTWA', () => ({
  getTWAInitData: () => initDataRef.current,
  isTWA: () => !!initDataRef.current,
}))
vi.mock('../../twaClient', () => ({ twaClient: { post: postSpy } }))
// i18n — passthrough ключей (модуль-ресурса рендерит заголовки хардкодом, не i18n).
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }))

import MeterEntryScreen from './MeterEntryScreen'

const resp = (status: number, payload: unknown) =>
  Promise.resolve({ ok: status < 400, status, json: () => Promise.resolve(payload) } as Response)

afterEach(() => {
  vi.unstubAllGlobals()
  postSpy.mockReset()
  initDataRef.current = 'INIT'
})

describe('MeterEntryScreen', () => {
  it('без initData → просит открыть через бота (не зовёт mint)', () => {
    initDataRef.current = ''
    render(
      <MemoryRouter initialEntries={['/twa/meter-entry']}>
        <MeterEntryScreen />
      </MemoryRouter>,
    )
    expect(screen.getByText('resourceAccounting.openViaBot')).toBeInTheDocument()
    expect(postSpy).not.toHaveBeenCalled()
  })

  it('валидная сессия (/v1/auth/me 200) → монтирует экран ввода показаний', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL) => {
        const url = String(input)
        if (url.includes('/v1/auth/me'))
          return resp(200, { data: { role: 'resource_meter_entry', display_name: 'K' } })
        return resp(200, { data: [] })
      }),
    )
    render(
      <MemoryRouter initialEntries={['/twa/meter-entry']}>
        <MeterEntryScreen />
      </MemoryRouter>,
    )
    expect(await screen.findByRole('heading', { name: 'Ввод показаний' })).toBeInTheDocument()
  })

  it('нет сессии (401) → mint по initData через twaClient', async () => {
    let me = 0
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL) => {
        const url = String(input)
        if (url.includes('/v1/auth/me')) {
          me += 1
          return me === 1
            ? resp(401, { data: null })
            : resp(200, { data: { role: 'resource_meter_entry', display_name: 'K' } })
        }
        return resp(200, { data: [] })
      }),
    )
    postSpy.mockResolvedValue({ data: { ticket: 'T', expires_in: 60 } })

    render(
      <MemoryRouter initialEntries={['/twa/meter-entry']}>
        <MeterEntryScreen />
      </MemoryRouter>,
    )

    await waitFor(() =>
      expect(postSpy).toHaveBeenCalledWith('/api/v2/resource-accounting/twa-ticket', {
        init_data: 'INIT',
      }),
    )
  })
})
