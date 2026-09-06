import { describe, it, expect, beforeEach, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { render, screen, waitFor } from '../../test/test-utils'
import { server } from '../../test/msw/server'
import { useAuthStore } from '../../stores/authStore'
import { configDraftFrom, configDraftToPayload, isValidStages } from '../../utils/elevatorsConfigForm'
import type { ElevatorsConfigOut } from '../../types/elevators'
import ElevatorsConfigPage from './ElevatorsConfigPage'

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}))

const CONFIG: ElevatorsConfigOut = {
  module_public: false,
  downtime_threshold_days: { not_working: 2, under_repair: 14 },
  resident_notifications: { repair_started: true, maintenance_started: false, back_in_service: true },
  staff_reminders: { maintenance: [30, 7, 1], certification: [60, 30], contract: [90], overdue_weekly: false },
}

beforeEach(() => {
  useAuthStore.setState({ user: { id: 1, roles: ['manager'] }, isAuthenticated: true, hydrating: false })
})

describe('ElevatorsConfigPage', () => {
  it('рендерит черновик из GET; пустой порог → null («не напоминать»), стадии парсятся', async () => {
    let body: Record<string, unknown> | null = null
    server.use(
      http.get('*/api/v2/elevators/config', () => HttpResponse.json(CONFIG)),
      http.put('*/api/v2/elevators/config', async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>
        return HttpResponse.json({ ...CONFIG, downtime_threshold_days: { not_working: 2, under_repair: null } })
      }),
    )
    const user = userEvent.setup()
    render(<ElevatorsConfigPage />)
    const underRepair = await screen.findByLabelText('В ремонте — напоминать через, дней')
    expect(underRepair).toHaveValue(14)
    expect(screen.getByLabelText('Техобслуживание')).toHaveValue('30, 7, 1')
    // T16: тумблер публичного виджета редактируемый и уходит в PUT.
    const modulePublic = screen.getByLabelText(/Показывать лифты жителям/)
    expect(modulePublic).not.toBeDisabled()
    expect(modulePublic).not.toBeChecked()
    await user.click(modulePublic)

    await user.clear(underRepair)
    await user.clear(screen.getByLabelText('Договор'))
    await user.type(screen.getByLabelText('Договор'), '45; 10 3')
    await user.click(screen.getByLabelText('Еженедельно напоминать о просроченном'))
    await user.click(screen.getByRole('button', { name: 'Сохранить' }))
    await waitFor(() => expect(body).not.toBeNull())
    expect(body).toEqual({
      module_public: true,
      downtime_threshold_days: { not_working: 2, under_repair: null },
      resident_notifications: { repair_started: true, maintenance_started: false, back_in_service: true },
      staff_reminders: { maintenance: [30, 7, 1], certification: [60, 30], contract: [45, 10, 3], overdue_weekly: true },
    })
  })

  it('мусор в стадиях — ошибка на клиенте, PUT не уходит', async () => {
    let posted = false
    server.use(
      http.get('*/api/v2/elevators/config', () => HttpResponse.json(CONFIG)),
      http.put('*/api/v2/elevators/config', () => {
        posted = true
        return HttpResponse.json(CONFIG)
      }),
    )
    const user = userEvent.setup()
    render(<ElevatorsConfigPage />)
    const stages = await screen.findByLabelText('Освидетельствование')
    await user.clear(stages)
    await user.type(stages, '30, abc')
    await user.click(screen.getByRole('button', { name: 'Сохранить' }))
    expect(screen.getByRole('alert')).toHaveTextContent('Стадии напоминаний — целые неотрицательные числа')
    expect(posted).toBe(false)
  })
})

describe('elevatorsConfigForm (чистые функции)', () => {
  it('isValidStages', () => {
    expect(isValidStages('')).toBe(true)
    expect(isValidStages('30, 7, 1')).toBe(true)
    expect(isValidStages('30;7 1')).toBe(true)
    expect(isValidStages('30, abc')).toBe(false)
    expect(isValidStages('-5')).toBe(false)
  })

  it('draft ↔ payload: null-порог = пустая строка и обратно', () => {
    const draft = configDraftFrom({ ...CONFIG, downtime_threshold_days: { not_working: null, under_repair: 3 } })
    expect(draft.module_public).toBe(false)
    expect(draft.not_working).toBe('')
    expect(draft.under_repair).toBe('3')
    const payload = configDraftToPayload({ ...draft, maintenance: ' 30 , 7,1 ' })
    expect(payload.module_public).toBe(false)
    expect(payload.downtime_threshold_days).toEqual({ not_working: null, under_repair: 3 })
    expect(payload.staff_reminders?.maintenance).toEqual([30, 7, 1])
  })
})
