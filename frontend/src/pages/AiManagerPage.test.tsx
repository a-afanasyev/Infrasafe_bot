import { describe, it, expect, beforeEach } from 'vitest'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { screen, waitFor } from '@testing-library/react'
import { render } from '../test/test-utils'
import { server } from '../test/msw/server'
import AiManagerPage from './AiManagerPage'

const TEMPLATE_KEYS = [
  'sla.executor_overdue', 'sla.staff_group', 'sla.manager_overdue', 'sla.reassign_failed', 'sla.reassigned_old',
  'sla.clarification_reminder', 'sla.clarification_manager', 'sla.executed_unconfirmed', 'sla.auto_accepted',
  'sla.critical_unassigned', 'public.assigned', 'public.executed',
]
const TEMPLATE_DEFAULTS = Object.fromEntries(TEMPLATE_KEYS.map((k) => [k, {
  ru: `RU ${k} {request_number}`, uz: `UZ ${k} {request_number}`, placeholders: ['request_number'],
}]))

const CONFIG = {
  enabled: true, mode: 'ai', window_start: '20:00', window_end: '08:00', timezone: 'Asia/Tashkent',
  max_requests_per_run: 10, sla_hours: { critical: 4, high: 24, medium: 72, low: 168 },
  ai: { min_confidence: 0.7, clarify_enabled: true, dedup_enabled: true, triage_instructions: '', news_instructions: '',
        extra_emergency_keywords: [], templates: {} },
  sla: { in_progress_max: { low: 72, medium: 48, high: 12, critical: 2 }, clarification_max: 48,
         executed_unconfirmed_max: 24, completed_unaccepted_days: 3, critical_unassigned_minutes: 30,
         ladder: { remind_executor: 0, staff_group: 2, manager: 4, reassign: 8 },
         ladder_enabled: { remind_executor: true, staff_group: true, manager: true, reassign: true },
         public_status: { enabled: true, min_urgency: 'critical' } },
  ai_available: true, ai_status: { open: true, open_ttl: 300, failures: 3 },
  template_defaults: TEMPLATE_DEFAULTS, base_emergency_keywords: ['газ', 'затоп'],
}

beforeEach(() => {
  server.use(http.get('*/api/v2/auto-manager-config', () => HttpResponse.json(CONFIG)))
})

describe('AiManagerPage', () => {
  it('saves instructions, extra keywords and a template override in one PUT without read-only fields', async () => {
    let body: Record<string, unknown> | null = null
    server.use(http.put('*/api/v2/auto-manager-config', async ({ request }) => {
      body = (await request.json()) as Record<string, unknown>
      return HttpResponse.json({ ...CONFIG, ...body })
    }))
    const user = userEvent.setup()
    render(<AiManagerPage />)
    await user.type(await screen.findByLabelText('Инструкции для триажа заявок'), 'Шум — не аварийно.')
    await user.type(screen.getByLabelText('Инструкции для анализа новостей об отключениях'), '7-й корпус')
    const extra = screen.getByLabelText(/Дополнительные аварийные слова/)
    await user.clear(extra)
    await user.type(extra, 'шлагбаум, искра')
    expect(screen.getByText(/Базовые аварийные слова.*газ, затоп/)).toBeInTheDocument()
    await user.click(screen.getByText('Тексты уведомлений'))
    await user.type(screen.getByLabelText('В чат дома: исполнитель выехал RU'), 'Выехали по №{{request_number}')   // `{{` = литерал `{` в user-event
    await user.click(screen.getByText('Сохранить правила'))
    await waitFor(() => expect(body).not.toBeNull())
    expect(body!.mode).toBe('ai')
    expect(body!.ai).toMatchObject({
      triage_instructions: 'Шум — не аварийно.', news_instructions: '7-й корпус',
      extra_emergency_keywords: ['шлагбаум', 'искра'],
      templates: { 'public.assigned': { ru: 'Выехали по №{request_number}' } },
    })
    for (const key of ['ai_available', 'ai_status', 'template_defaults', 'base_emergency_keywords']) {
      expect(body).not.toHaveProperty(key)
    }
  })

  it('shows the breaker banner and resets it', async () => {
    let reset = 0
    server.use(http.post('*/api/v2/auto-manager-config/ai-breaker/reset', () => {
      reset += 1
      return HttpResponse.json({ open: false, open_ttl: 0, failures: 0 })
    }))
    const user = userEvent.setup()
    render(<AiManagerPage />)
    expect(await screen.findByText(/ИИ временно в режиме правил ещё 5 мин/)).toBeInTheDocument()
    await user.click(screen.getByText('Сбросить предохранитель'))
    await waitFor(() => expect(reset).toBe(1))
  })

  it('explains unavailability and disables the AI mode button when ai_available is false', async () => {
    server.use(http.get('*/api/v2/auto-manager-config', () =>
      HttpResponse.json({ ...CONFIG, mode: 'rule', ai_available: false, ai_status: null })))
    render(<AiManagerPage />)
    expect(await screen.findByText(/ИИ-режим недоступен на этой площадке/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '🤖 ИИ' })).toBeDisabled()
    expect(screen.queryByText(/Сбросить предохранитель/)).not.toBeInTheDocument()
  })

  it('switching mode to "Выключен" saves enabled=false', async () => {
    let body: Record<string, unknown> | null = null
    server.use(http.put('*/api/v2/auto-manager-config', async ({ request }) => {
      body = (await request.json()) as Record<string, unknown>
      return HttpResponse.json({ ...CONFIG, ...body })
    }))
    const user = userEvent.setup()
    render(<AiManagerPage />)
    await user.click(await screen.findByRole('button', { name: 'Выключен' }))
    await user.click(screen.getByText('Сохранить правила'))
    await waitFor(() => expect(body).not.toBeNull())
    expect(body).toMatchObject({ enabled: false, mode: 'ai' })
  })
})
