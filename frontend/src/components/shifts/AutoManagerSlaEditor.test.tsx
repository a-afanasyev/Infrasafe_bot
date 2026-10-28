import { describe, it, expect, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
import { render, screen } from '../../test/test-utils'
import SlaEditor from './AutoManagerSlaEditor'
import type { AutoManagerSlaConfig } from '../../types/autoManagerConfig'

const SLA: AutoManagerSlaConfig = {
  in_progress_max: { low: 72, medium: 48, high: 12, critical: 2 },
  clarification_max: 48,
  executed_unconfirmed_max: 24,
  completed_unaccepted_days: 3,
  critical_unassigned_minutes: 30,
  ladder: { remind_executor: 0, staff_group: 2, manager: 4, reassign: 8 },
  ladder_enabled: { remind_executor: true, staff_group: true, manager: true, reassign: true },
  public_status: { enabled: true, min_urgency: 'critical' },
}

describe('AutoManagerSlaEditor', () => {
  it('shows the save button only when onSave is given', () => {
    const { unmount } = render(<SlaEditor value={SLA} pending={false} onSave={() => {}} />)
    expect(screen.getByText('Сохранить SLA')).toBeInTheDocument()
    unmount()
    render(<SlaEditor value={SLA} onChange={() => {}} />)
    expect(screen.queryByText('Сохранить SLA')).not.toBeInTheDocument()
  })

  it('reports step toggles and public-status threshold through onChange', async () => {
    const onChange = vi.fn()
    const user = userEvent.setup()
    render(<SlaEditor value={SLA} onChange={onChange} />)
    const toggles = screen.getAllByLabelText('Ступень включена')
    expect(toggles).toHaveLength(4)
    await user.click(toggles[1])   // staff_group
    expect(onChange).toHaveBeenLastCalledWith({
      ...SLA, ladder_enabled: { ...SLA.ladder_enabled, staff_group: false },
    })
    await user.selectOptions(screen.getByLabelText('Минимальная срочность'), 'high')
    expect(onChange).toHaveBeenLastCalledWith({   // черновик накапливает оба изменения
      ...SLA, ladder_enabled: { ...SLA.ladder_enabled, staff_group: false },
      public_status: { enabled: true, min_urgency: 'high' },
    })
    expect(screen.getByText(/Отключённая ступень считается пройденной/)).toBeInTheDocument()
  })
})
