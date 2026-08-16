import { describe, it, expect, beforeEach } from 'vitest'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { screen, waitFor } from '@testing-library/react'
import { render } from '../../test/test-utils'
import { server } from '../../test/msw/server'
import AutoManagerToggle from './AutoManagerToggle'

// Тумблер вынесен из AutoManagerCard, чтобы жить ещё и в топбаре канбана:
// менеджер выключает автоназначение там, где смотрит на заявки, а не в разделе
// дежурств. Разметка и строки сохранены дословно — синхронность двух копий
// обеспечивает общий queryKey ['auto-manager-config'].

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

describe('AutoManagerToggle', () => {
  it('renders the current state', async () => {
    render(<AutoManagerToggle />)

    expect(await screen.findByText('🟢 Включён')).toBeInTheDocument()
    expect(screen.getByRole('checkbox')).toBeChecked()
  })

  it('sends only the enabled patch on click', async () => {
    let body: Record<string, unknown> | null = null
    server.use(
      http.put('*/api/v2/auto-manager-config', async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>
        return HttpResponse.json({ ...CONFIG, enabled: false })
      }),
    )
    render(<AutoManagerToggle />)
    await screen.findByRole('checkbox')

    await userEvent.click(screen.getByRole('checkbox'))

    await waitFor(() => expect(body).not.toBeNull())
    expect(body).toMatchObject({ enabled: false })
  })

  it('renders nothing while loading', () => {
    const { container } = render(<AutoManagerToggle />)

    // До ответа сети в топбаре не должно быть полуживого контрола: тумблер в
    // неизвестном состоянии хуже отсутствующего — по нему нельзя понять,
    // раздаются заявки или нет.
    expect(container.querySelector('input[type="checkbox"]')).toBeNull()
  })

  it('renders nothing when the config request fails', async () => {
    server.use(
      http.get('*/api/v2/auto-manager-config', () => new HttpResponse(null, { status: 403 })),
    )
    const { container } = render(<AutoManagerToggle />)

    // 403 у роли без доступа к конфигу — молча ничего не показываем, а не
    // ошибку в шапке доски.
    await waitFor(() => expect(container.querySelector('input[type="checkbox"]')).toBeNull())
    expect(screen.queryByText('🟢 Включён')).not.toBeInTheDocument()
  })
})
