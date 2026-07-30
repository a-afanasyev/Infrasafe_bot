import { render, screen, waitFor } from '@testing-library/react'
import { I18nextProvider } from 'react-i18next'
import { MemoryRouter } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { testI18n } from '@/test/test-utils'

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

import MeterEntryScreen from './MeterEntryScreen'

// AUD6-P2-53: модуль-ресурса теперь на i18n — рендерим с реальным testI18n (ru).
const renderScreen = () =>
  render(
    <I18nextProvider i18n={testI18n}>
      <MemoryRouter initialEntries={['/twa/meter-entry']}>
        <MeterEntryScreen />
      </MemoryRouter>
    </I18nextProvider>,
  )

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
    renderScreen()
    expect(
      screen.getByText('Откройте этот экран через бота, чтобы авторизоваться.'),
    ).toBeInTheDocument()
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
    renderScreen()
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

    renderScreen()

    await waitFor(() =>
      expect(postSpy).toHaveBeenCalledWith('/api/v2/resource-accounting/twa-ticket', {
        init_data: 'INIT',
      }),
    )
  })
})
