import { describe, it, expect } from 'vitest'
import { render, screen } from '../../test/test-utils'
import KanbanColumn from './KanbanColumn'
import type { RequestCard as TCard } from '../../hooks/useKanban'

// AUD8-FE-02: у обрезанной терминальной колонки подпись «показано X из Y»
// рендерилась сырым ключом kanban.truncatedColumn — его не было в локалях.

const card: TCard = {
  request_number: 'A-1', status: 'Принято', category: 'electricity', urgency: 'medium', source: 'web',
  description: null, address: null, executor_id: null, executor_name: null, notes: null,
  completion_report: null, requested_materials: null, return_reason: null, manager_return_reason: null,
  created_at: '2026-09-19T08:00:00Z', updated_at: null, manager_confirmed: false,
  elevator_id: null, elevator_label: null, elevator_status: null,
}

describe('KanbanColumn', () => {
  it('обрезанная колонка показывает «Показано 1 из 5», а не ключ', () => {
    render(
      <KanbanColumn
        column={{ status: 'Принято', count: 5, requests: [card] }}
        onCardClick={() => {}}
        activeDragStatus={null}
        overColumnId={null}
        overItemId={null}
      />,
    )
    expect(screen.getByText('Показано 1 из 5')).toBeInTheDocument()
    expect(screen.queryByText(/truncatedColumn/)).toBeNull()
  })
})
