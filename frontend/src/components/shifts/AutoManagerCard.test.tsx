import { describe, it, expect, beforeEach, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { toast } from 'sonner'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render as rtlRender, screen, waitFor } from '@testing-library/react'
import { I18nextProvider } from 'react-i18next'
import { MemoryRouter } from 'react-router-dom'
import { render, testI18n } from '../../test/test-utils'
import { server } from '../../test/msw/server'
import AutoManagerCard from './AutoManagerCard'

// Renders with a queryClient the test controls directly, so a "background
// update" can be simulated via `queryClient.setQueryData` instead of racing
// the hook's real 30s `refetchInterval` (which is flaky to fake-time under
// MSW). Same provider stack as ../../test/test-utils.tsx's AllProviders.
function renderWithClient(queryClient: QueryClient) {
  return rtlRender(
    <QueryClientProvider client={queryClient}>
      <I18nextProvider i18n={testI18n}>
        <MemoryRouter>
          <AutoManagerCard />
        </MemoryRouter>
      </I18nextProvider>
    </QueryClientProvider>,
  )
}

const CONFIG = {
  enabled: true,
  mode: 'rule' as const,
  window_start: '20:00',
  window_end: '08:00',
  timezone: 'Asia/Tashkent',
  max_requests_per_run: 10,
}

beforeEach(() => {
  server.use(http.get('*/api/v2/auto-manager-config', () => HttpResponse.json(CONFIG)))
})

describe('AutoManagerCard', () => {
  it('renders current config values (enabled, timezone, max requests, mode)', async () => {
    render(<AutoManagerCard />)
    await screen.findByText('🤖 Автоматический менеджер')
    expect(screen.getByText('🟢 Включён')).toBeInTheDocument()
    expect(screen.getByText('Asia/Tashkent')).toBeInTheDocument()
    expect(screen.getByText('10')).toBeInTheDocument()
    expect(screen.getByText('📐 По правилу')).toBeInTheDocument()
    expect(screen.getByText('🤖 ИИ (скоро)')).toBeInTheDocument()
  })

  it('toggling enabled fires the mutation with a COMPLETE config (all 6 fields, just enabled flipped)', async () => {
    let body: Record<string, unknown> | null = null
    server.use(
      http.put('*/api/v2/auto-manager-config', async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>
        return HttpResponse.json(body)
      }),
    )
    const user = userEvent.setup()
    render(<AutoManagerCard />)
    const toggle = await screen.findByLabelText('Включить/выключить автоменеджер')
    await user.click(toggle)

    await waitFor(() => expect(body).not.toBeNull())
    expect(body).toEqual({ ...CONFIG, enabled: false })
  })

  it('the AI mode button is clickable and shows a hint, but never writes to the config', async () => {
    // Changed from HTML-disabled to an interactive click-shows-hint button
    // (per explicit follow-up request) — must still NEVER persist mode="ai"
    // in Phase 1, no matter how many times it's clicked.
    let putCalled = false
    server.use(
      http.put('*/api/v2/auto-manager-config', () => {
        putCalled = true
        return HttpResponse.json(CONFIG)
      }),
    )
    const infoSpy = vi.spyOn(toast, 'info')
    const user = userEvent.setup()
    render(<AutoManagerCard />)
    const aiButton = await screen.findByText('🤖 ИИ (скоро)')
    expect(aiButton).not.toBeDisabled()

    await user.click(aiButton)
    await user.click(aiButton)

    expect(infoSpy).toHaveBeenCalledTimes(2)
    expect(infoSpy).toHaveBeenCalledWith('ИИ-режим появится позже, работает режим по правилу')
    expect(putCalled).toBe(false)
    expect(screen.getByText('📐 По правилу')).toBeInTheDocument()
    expect(screen.getByText('🟢 Включён')).toBeInTheDocument()
  })

  it('saving a malformed window is caught client-side (no PUT fires)', async () => {
    let putCalled = false
    server.use(
      http.put('*/api/v2/auto-manager-config', () => {
        putCalled = true
        return HttpResponse.json(CONFIG)
      }),
    )
    const user = userEvent.setup()
    render(<AutoManagerCard />)
    const startInput = await screen.findByLabelText('С')
    // jsdom's <input type="time"> coerces free-typed garbage into a valid
    // HH:MM (unlike a real browser widget), so the only reliably-malformed
    // state reachable via userEvent is clearing the field to ''.
    await user.clear(startInput)
    expect((startInput as HTMLInputElement).value).toBe('')

    const saveButton = screen.getByRole('button', { name: 'Сохранить окно' })
    expect(saveButton).not.toBeDisabled()
    await user.click(saveButton)
    expect(screen.getByText('Неверный формат времени (ЧЧ:ММ)')).toBeInTheDocument()
    expect(putCalled).toBe(false)
  })

  it('an unsaved window edit survives a background refetch triggered by another field changing', async () => {
    // Regression: useAutoManagerConfig polls every 30s (deliberately, so the
    // bot's toggle and this card stay in sync). A naive "reseed draft
    // whenever `data` reference changes" effect would silently discard an
    // in-progress, unsaved window edit whenever ANY field changed
    // server-side (e.g. `enabled` flipped from the bot) — not just when the
    // window itself changed. Simulate the background update directly via
    // the query cache rather than racing the real 30s interval.
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
    })
    const user = userEvent.setup()
    renderWithClient(queryClient)

    const startInput = await screen.findByLabelText('С')
    await user.clear(startInput)
    await user.type(startInput, '21:00')
    expect((startInput as HTMLInputElement).value).toBe('21:00')

    // Simulate the background poll landing with `enabled` flipped (e.g. by
    // the bot) — window fields unchanged server-side.
    queryClient.setQueryData(['auto-manager-config'], { ...CONFIG, enabled: false })
    await waitFor(() => expect(screen.getByText('🔴 Выключен')).toBeInTheDocument())

    // The user's unsaved keystroke must still be there — not clobbered back
    // to the server's original '20:00'.
    expect((startInput as HTMLInputElement).value).toBe('21:00')
  })

  it('saving the window does not revert a more recent bot-side enabled change', async () => {
    // The exact scenario reported: bot flips enabled=false->true server-side;
    // dashboard (rendered with the OLD enabled=false still in its component
    // state) then saves only the window. The PUT must carry the FRESH
    // enabled=true, not silently revert it back to false.
    const STARTING_CONFIG = { ...CONFIG, enabled: false }
    server.use(http.get('*/api/v2/auto-manager-config', () => HttpResponse.json(STARTING_CONFIG)))

    let putBody: Record<string, unknown> | null = null
    const user = userEvent.setup()
    render(<AutoManagerCard />)
    await screen.findByText('🔴 Выключен')

    // Bot changes `enabled` server-side while the dashboard is still showing
    // the old value (no re-render has happened yet — this is exactly what a
    // stale 30s-old poll would look like from the component's perspective).
    server.use(
      http.get('*/api/v2/auto-manager-config', () => HttpResponse.json({ ...CONFIG, enabled: true })),
      http.put('*/api/v2/auto-manager-config', async ({ request }) => {
        putBody = (await request.json()) as Record<string, unknown>
        return HttpResponse.json(putBody)
      }),
    )

    const startInput = await screen.findByLabelText('С')
    await user.clear(startInput)
    await user.type(startInput, '21:30')
    const saveButton = screen.getByRole('button', { name: 'Сохранить окно' })
    await user.click(saveButton)

    await waitFor(() => expect(putBody).not.toBeNull())
    expect((putBody as unknown as { enabled: boolean }).enabled).toBe(true)
    expect((putBody as unknown as { window_start: string }).window_start).toBe('21:30')
  })

  it('shows an error toast (not a crash) when the GET fails', async () => {
    server.use(http.get('*/api/v2/auto-manager-config', () => new HttpResponse(null, { status: 500 })))
    render(<AutoManagerCard />)
    await screen.findByText('🤖 Автоматический менеджер')
    expect(screen.getByText('Не удалось загрузить конфиг авто-менеджера')).toBeInTheDocument()
  })
})
