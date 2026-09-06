import { describe, it, expect } from 'vitest'
import { render, screen } from '../../test/test-utils'
import CreateRepairDialog from './CreateRepairDialog'
import type { ElevatorDetail, ElevatorStatus } from '../../types/elevators'

// Р18 (§7): персоналу «Создать ремонт» не блокируется, но если лифт уже
// «В ремонте»/«На ТО» — предупреждение о возможном дубле текущих работ.

function detail(status: ElevatorStatus, statusSince: string | null = null): ElevatorDetail {
  return {
    id: 7,
    label: 'Лифт 1, подъезд 2',
    building_id: 12,
    building_address: 'ул. Ленина 1',
    current_status: status,
    status_since: statusSince,
  } as unknown as ElevatorDetail
}

function renderDialog(elevator: ElevatorDetail) {
  render(<CreateRepairDialog elevator={elevator} open onClose={() => {}} />)
}

describe('CreateRepairDialog — предупреждение Р18', () => {
  it('лифт «В ремонте»: предупреждение со статусом и датой, кнопка не блокируется', () => {
    renderDialog(detail('under_repair', '2026-09-01T07:30:00Z'))
    const alert = screen.getByRole('alert')
    expect(alert).toHaveTextContent(/В ремонте/)
    expect(alert).toHaveTextContent(/текущие работы/)
    expect(screen.getByRole('button', { name: 'Создать заявку' })).toBeInTheDocument()
  })

  it('лифт «На ТО» без момента смены статуса: текст без «с …»', () => {
    renderDialog(detail('maintenance'))
    const alert = screen.getByRole('alert')
    expect(alert).toHaveTextContent(/Техобслуживание/)
    expect(alert.textContent).not.toMatch(/ с /)
  })

  it('лифт «не работает»: предупреждения нет (Р18 его не считает работами)', () => {
    renderDialog(detail('not_working'))
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('лифт «работает»: предупреждения нет', () => {
    renderDialog(detail('working'))
    expect(screen.queryByRole('alert')).toBeNull()
  })
})
