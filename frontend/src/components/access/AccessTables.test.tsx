import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { I18nextProvider } from 'react-i18next'
import { testI18n } from '../../test/test-utils'
import AccessEventsTable from './AccessEventsTable'
import VehiclesTable from './VehiclesTable'
import PassesTable from './PassesTable'
import RequestsTable from './RequestsTable'
import type {
  AccessEventRow,
  VehicleRow,
  PassRow,
  AccessRequestRow,
} from '../../types/access'

function wrap(node: React.ReactNode) {
  return render(<I18nextProvider i18n={testI18n}>{node}</I18nextProvider>)
}

const event: AccessEventRow = {
  id: 42,
  event_id: 'E-42',
  controller_id: 1,
  zone_id: 7,
  gate_id: 3,
  direction: 'entry',
  plate_number_normalized: '01A777BC',
  captured_at: '2026-06-26T10:00:00Z',
  occurred_at: '2026-06-26T10:00:00Z',
  source: 'anpr',
  decision: 'allow',
  status: 'allowed',
  reason: 'permanent_vehicle_allowed',
  decision_id: 5,
  resolved_by_user_id: null,
  has_command: true,
}

describe('AccessEventsTable', () => {
  it('рендерит строку события с полным номером, решением и местом', () => {
    wrap(<AccessEventsTable events={[event]} />)
    expect(screen.getByText('01A777BC')).toBeInTheDocument()
    // «Разрешён» встречается дважды: бейдж решения (allow) и колонка статуса
    // (allowed) — обе ячейки переведены одинаково.
    expect(screen.getAllByText('Разрешён').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('ТС в постоянном списке')).toBeInTheDocument() // reason
    expect(screen.getByText('Зона 7 · Точка 3')).toBeInTheDocument()
  })

  it('клик по строке вызывает onRowClick с событием', () => {
    const onRowClick = vi.fn()
    wrap(<AccessEventsTable events={[event]} onRowClick={onRowClick} />)
    fireEvent.click(screen.getByText('01A777BC'))
    expect(onRowClick).toHaveBeenCalledWith(event)
  })

  it('пустой список → пустое состояние', () => {
    wrap(<AccessEventsTable events={[]} />)
    expect(screen.getByText('События не найдены')).toBeInTheDocument()
  })
})

const vehicle: VehicleRow = {
  id: 7,
  plate_number_original: '01A123BC',
  plate_number_normalized: '01A123BC',
  plate_country: 'UZ',
  plate_type: null,
  brand: 'Chevrolet',
  model: 'Cobalt',
  color: 'белый',
  vehicle_class: 'B',
  status: 'active',
  blocked_reason: null,
  blocked_by_user_id: null,
  blocked_at: null,
  apartments: [
    {
      apartment_id: 101,
      relation_type: 'owner',
      status: 'active',
      valid_from: null,
      valid_until: null,
      approved_by_user_id: null,
      approved_at: null,
    },
  ],
}

describe('VehiclesTable', () => {
  it('рендерит строку авто с маркой/моделью и статусом', () => {
    wrap(<VehiclesTable vehicles={[vehicle]} />)
    expect(screen.getByText('01A123BC')).toBeInTheDocument()
    expect(screen.getByText('Chevrolet Cobalt')).toBeInTheDocument()
    expect(screen.getByText('Активен')).toBeInTheDocument() // status badge
    expect(screen.getByText('101')).toBeInTheDocument() // apartment link
  })
})

const pass: PassRow = {
  id: 3,
  pass_type: 'taxi',
  apartment_id: 55,
  created_by_user_id: 1,
  zone_id: null,
  plate_number_original: '30Z999XX',
  plate_number_normalized: '30Z999XX',
  valid_from: '2026-06-26T08:00:00Z',
  valid_until: '2026-06-26T20:00:00Z',
  max_entries: 2,
  used_entries: 1,
  status: 'active',
  source: 'manual',
  created_at: '2026-06-26T07:00:00Z',
}

describe('PassesTable', () => {
  it('рендерит строку пропуска с типом и счётчиком проездов', () => {
    wrap(<PassesTable passes={[pass]} />)
    expect(screen.getByText('Такси')).toBeInTheDocument() // passType.taxi
    expect(screen.getByText('30Z999XX')).toBeInTheDocument()
    expect(screen.getByText('1/2')).toBeInTheDocument()
  })
})

const request: AccessRequestRow = {
  id: 9,
  apartment_id: 12,
  created_by_user_id: 2,
  vehicle_id: null,
  plate_number_original: '40K111LM',
  plate_number_normalized: '40K111LM',
  relation_type: 'family',
  status: 'pending',
  reviewed_by_user_id: null,
  reviewed_at: null,
  review_comment: null,
  created_at: '2026-06-26T06:00:00Z',
}

describe('RequestsTable', () => {
  it('рендерит строку заявки со статусом «Ожидает»', () => {
    wrap(<RequestsTable requests={[request]} />)
    expect(screen.getByText('40K111LM')).toBeInTheDocument()
    expect(screen.getByText('Ожидает')).toBeInTheDocument() // status pending
  })
})
