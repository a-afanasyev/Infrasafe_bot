import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { http, HttpResponse, delay } from 'msw'
import { afterEach, describe, expect, it } from 'vitest'

import { server } from '../test/msw/server'
import { DEFAULT_DISPLAY_TZ, getDisplayTz, setDisplayTz } from '../utils/timezone'
import { resolveDisplayTz, useDisplayTz } from './displayTz'
import { DisplayTzProvider } from './DisplayTzProvider'

// ARCH-137 B6: провайдер гейтит рендер до первого разрешения запроса и при
// ЛЮБОЙ деградации (ошибка сети, 200 без поля, мусорная зона) отдаёт дефолт,
// не блокируя рендер. Контракт «фронт впереди бэка» — как WorkReportsPage.

function Probe() {
  const tz = useDisplayTz()
  return <div data-testid="tz">{tz}</div>
}

function renderProvider() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <DisplayTzProvider fallback={<div data-testid="gate">loading</div>}>
        <Probe />
      </DisplayTzProvider>
    </QueryClientProvider>,
  )
}

afterEach(() => setDisplayTz(DEFAULT_DISPLAY_TZ))

describe('resolveDisplayTz', () => {
  it('берёт валидную зону из ответа', () => {
    expect(resolveDisplayTz({ display_tz: 'Europe/London' })).toBe('Europe/London')
  })
  it('деградирует в дефолт: нет поля / не строка / мусорная зона / не объект', () => {
    expect(resolveDisplayTz({})).toBe(DEFAULT_DISPLAY_TZ)
    expect(resolveDisplayTz({ display_tz: 42 })).toBe(DEFAULT_DISPLAY_TZ)
    expect(resolveDisplayTz({ display_tz: 'Not/AZone' })).toBe(DEFAULT_DISPLAY_TZ)
    expect(resolveDisplayTz(undefined)).toBe(DEFAULT_DISPLAY_TZ)
    expect(resolveDisplayTz(null)).toBe(DEFAULT_DISPLAY_TZ)
  })
})

describe('DisplayTzProvider', () => {
  it('гейтит детей до ответа, затем ставит зону из display_tz', async () => {
    server.use(
      http.get('*/api/v2/public/board-config', async () => {
        await delay(20)
        return HttpResponse.json({ display_tz: 'Europe/London' })
      }),
    )
    renderProvider()
    // До разрешения — fallback, детей нет.
    expect(screen.getByTestId('gate')).toBeInTheDocument()
    expect(screen.queryByTestId('tz')).toBeNull()

    expect(await screen.findByTestId('tz')).toHaveTextContent('Europe/London')
    expect(getDisplayTz()).toBe('Europe/London')
  })

  it('200 без поля (старый бэк на rolling deploy) → дефолт, рендер не блокирован', async () => {
    server.use(http.get('*/api/v2/public/board-config', () => HttpResponse.json({})))
    renderProvider()
    expect(await screen.findByTestId('tz')).toHaveTextContent(DEFAULT_DISPLAY_TZ)
    expect(getDisplayTz()).toBe(DEFAULT_DISPLAY_TZ)
  })

  it('мусорное значение зоны → дефолт', async () => {
    server.use(
      http.get('*/api/v2/public/board-config', () =>
        HttpResponse.json({ display_tz: 'Not/AZone' }),
      ),
    )
    renderProvider()
    expect(await screen.findByTestId('tz')).toHaveTextContent(DEFAULT_DISPLAY_TZ)
  })

  it('ошибка сети → дефолт, рендер не блокирован', async () => {
    server.use(http.get('*/api/v2/public/board-config', () => HttpResponse.error()))
    renderProvider()
    expect(await screen.findByTestId('tz')).toHaveTextContent(DEFAULT_DISPLAY_TZ)
    expect(getDisplayTz()).toBe(DEFAULT_DISPLAY_TZ)
  })
})
