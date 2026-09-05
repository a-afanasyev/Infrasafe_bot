export interface BalanceSnapshot {
  debt: string
  prepayment: string
  as_of: string
  source: string
  filename: string
  import_id: number
  line: number
  position?: number
  currency: string
}
export interface PaymentRow {
  operation_id: string
  paid_at: string
  amount: string
  source: string
  import_id: number
  note?: string
  currency?: string
}
export interface AccountBalance {
  status: 'available' | 'no_data' | 'no_account' | 'unavailable'
  account_number: string | null
  current: BalanceSnapshot | null
  history?: BalanceSnapshot[]
  payments?: PaymentRow[]
}
export interface PaymentImport {
  id: number
  kind: 'balances' | 'payments'
  source: string
  filename: string
  as_of: string
  status: 'preview' | 'active' | 'inactive'
  invalid: number
  row_count: number
  created_at: string
  rows?: { line: number; account_number: string; debt?: string; prepayment?: string; amount?: string; operation_id?: string; paid_at?: string; note?: string; errors: string[]; raw?: Record<string, string> }[]
  audit?: { action: string; actor_id: string; reason: string | null; created_at: string }[]
}
