import type { ElevatorCard, ElevatorDetail, ElevatorSummary } from '../../types/elevators'

/** Фикстуры модуля «Лифты» для страничных тестов (msw). */

export const ELEVATOR_CARD: ElevatorCard = {
  id: 7,
  building_id: 12,
  building_address: 'ул. Мирзо-Улугбека, 12',
  yard_id: 3,
  yard_name: 'Двор 3',
  entrance_number: 2,
  elevator_number: 1,
  label: 'Лифт 1, подъезд 2',
  current_status: 'working',
  status_since: '2026-09-01T08:00:00Z',
  is_commissioned: true,
  archived_at: null,
  is_public: true,
  flags: { no_contract: false, cert_expired: true, maintenance_overdue: false },
  availability_30d: 0.973,
  open_requests_count: 2,
}

export const ELEVATOR_DETAIL: ElevatorDetail = {
  ...ELEVATOR_CARD,
  passport_number: 'P-001',
  manufacturer: 'OTIS',
  serial_number: 'SN-777',
  factory_number: 'F-1',
  model: 'Gen2',
  production_year: 2015,
  capacity_kg: 630,
  floors_served: '1-9',
  commissioned_at: '2016-01-10',
  downtime_reason: null,
  spare_part_expected_on: null,
  publish_downtime_details: false,
  service_org_name: 'ЛифтСервис',
  service_org_phone: '+998901234567',
  contract_number: 'C-42',
  contract_until: '2027-01-01',
  cert_number: 'CERT-9',
  cert_valid_until: '2026-01-01',
  cert_act_url: 'https://example.org/act.pdf',
  public_code: 'ABC123',
  archived_reason: null,
  apartments_without_entrance_count: 4,
  version: 3,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-09-01T08:00:00Z',
}

export const ELEVATOR_SUMMARY: ElevatorSummary = {
  today: '2026-09-05',
  totals: {
    total: 5,
    by_status: { working: 3, not_working: 1, under_repair: 1, maintenance: 0 },
    no_contract: 1,
    cert_expired: 2,
    maintenance_overdue: 1,
    downtime_over_threshold: 1,
  },
  yards: [],
  requests_without_elevator: 3,
  downtime_threshold_days: { not_working: 2, under_repair: 14 },
}
