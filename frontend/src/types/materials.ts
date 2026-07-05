/**
 * Типы модуля складского учёта материалов (/api/v2/materials).
 *
 * Числовые поля (qty/цены/суммы) приходят строками — pydantic сериализует
 * Decimal в str; форматирование в utils/materialsFormat.ts.
 */

export type MaterialUnit = 'pcs' | 'm' | 'm2' | 'l' | 'kg' | 'pack' | 'set'

export const MATERIAL_UNITS: readonly MaterialUnit[] = [
  'pcs', 'm', 'm2', 'l', 'kg', 'pack', 'set',
] as const

export interface MaterialCard {
  id: number
  name: string
  unit: MaterialUnit
  category: string | null
  min_stock: string | null
  is_active: boolean
  created_at: string | null
}

export interface MaterialsFilters {
  q?: string
  is_active?: boolean
  limit?: number
  offset?: number
}

export interface CreateMaterialPayload {
  name: string
  unit: MaterialUnit
  category?: string
  min_stock?: string
}

export interface UpdateMaterialPayload {
  name?: string
  unit?: MaterialUnit
  category?: string
  min_stock?: string | null
  is_active?: boolean
}

export interface StockRow {
  material_id: number
  name: string
  unit: MaterialUnit
  category: string | null
  min_stock: string | null
  stock: string
  stock_value: string
  low_stock: boolean
}

export interface CreateReceiptPayload {
  material_id: number
  qty: string
  unit_price: string
  supplier?: string
  doc_number?: string
  doc_date?: string
  note?: string
}

export interface CreateIssuePayload {
  material_id: number
  qty: string
  doc_type: 'request' | 'household'
  request_number?: string
  reason?: string
}

export interface CreateAdjustmentPayload {
  material_id: number
  direction: 'surplus' | 'shortage'
  reason: string
  qty?: string
  unit_price?: string
  reversal_of_issue_id?: number
  reversal_of_receipt_id?: number
}

export interface OperationRow {
  op_type: 'receipt' | 'issue'
  id: number
  material_id: number
  material_name: string
  unit: MaterialUnit
  doc_type: string
  qty: string
  amount: string
  request_number: string | null
  supplier: string | null
  reason: string | null
  created_by: number
  created_at: string | null
}

export interface OperationsPage {
  total: number
  items: OperationRow[]
}

export interface OperationsFilters {
  op_type?: 'receipt' | 'issue'
  material_id?: number
  request_number?: string
  date_from?: string
  date_to?: string
  limit?: number
  offset?: number
}

export interface IssueCard {
  id: number
  material_id: number
  doc_type: string
  qty: string
  total_cost: string
  request_number: string | null
  reason: string | null
  material_name: string
  unit: MaterialUnit
  created_by: number
  created_at: string | null
  /** by-request: расход полностью сторнирован (не входит в total_cost) */
  is_reversed?: boolean
}

export interface RequestMaterialsOut {
  request_number: string
  items: IssueCard[]
  total_cost: string
}

export interface ProcurementRow {
  material_id: number
  name: string
  unit: MaterialUnit
  stock: string
  min_stock: string
  to_buy: string
}

export interface OpenPurchaseRequest {
  request_number: string
  requested_materials: string | null
  executor_name: string | null
}

export interface ProcurementOut {
  deficit: ProcurementRow[]
  open_purchase_requests: OpenPurchaseRequest[]
}
