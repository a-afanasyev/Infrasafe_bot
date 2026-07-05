import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Package, Download, Plus, ArrowDownToLine, ArrowUpFromLine, Scale, Pencil, Undo2 } from 'lucide-react'
import { usePageTitle } from '../../hooks/usePageTitle'
import AccessTabBar from '../../components/access/AccessTabBar'
import AccessPagination from '../../components/access/AccessPagination'
import LoadingSpinner from '../../components/shared/LoadingSpinner'
import EmptyState from '../../components/shared/EmptyState'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import MaterialFormDialog from '../../components/materials/MaterialFormDialog'
import ReceiptDialog from '../../components/materials/ReceiptDialog'
import IssueDialog from '../../components/materials/IssueDialog'
import AdjustmentDialog from '../../components/materials/AdjustmentDialog'
import ReversalDialog from '../../components/materials/ReversalDialog'
import { useUnitLabel } from '../../hooks/useUnitLabel'
import {
  exportOperationsCsv,
  exportProcurementCsv,
  useMaterialOperations,
  useMaterials,
  useMaterialsStock,
  useProcurement,
} from '../../hooks/useMaterials'
import { fmtMoney, fmtQty } from '../../utils/materialsFormat'
import type {
  MaterialCard,
  OperationRow,
  OperationsFilters,
  StockRow,
} from '../../types/materials'

/**
 * Склад материалов (менеджер): вкладки «Остатки» | «Журнал операций» | «На закуп».
 * Операции append-only — исправления только сторно (кнопка на строке журнала).
 * Гард роута — MATERIALS_MODULE_ROLES (manager/system_admin).
 */
const PAGE_LIMIT = 50

type Tab = 'stock' | 'operations' | 'procurement'

function Th({ children }: { children?: React.ReactNode }) {
  return (
    <th className="px-3 py-2.5 text-left text-[10px] font-bold uppercase tracking-wider text-text-muted font-[family-name:var(--font-display)] whitespace-nowrap">
      {children}
    </th>
  )
}

function Td({ children, className = '' }: { children?: React.ReactNode; className?: string }) {
  return <td className={`px-3 py-2 text-[13px] text-text-primary ${className}`}>{children}</td>
}

export default function MaterialsPage() {
  const { t } = useTranslation()
  usePageTitle(t('materials.title'))
  const unitLabel = useUnitLabel()

  const [tab, setTab] = useState<Tab>('stock')
  const [stockQuery, setStockQuery] = useState('')
  const [onlyLow, setOnlyLow] = useState(false)
  const [opsFilters, setOpsFilters] = useState<OperationsFilters>({ limit: PAGE_LIMIT, offset: 0 })

  const [formMaterial, setFormMaterial] = useState<MaterialCard | null | undefined>(undefined) // undefined=закрыт, null=создание
  const [receiptOpen, setReceiptOpen] = useState(false)
  const [issueOpen, setIssueOpen] = useState(false)
  const [adjustmentOpen, setAdjustmentOpen] = useState(false)
  const [reversalOp, setReversalOp] = useState<OperationRow | null>(null)

  const stock = useMaterialsStock({ q: stockQuery || undefined, only_low: onlyLow || undefined })
  const materials = useMaterials({ limit: 200 })
  const operations = useMaterialOperations(opsFilters)
  const procurement = useProcurement()

  const materialById = new Map((materials.data ?? []).map((m) => [m.id, m]))

  const patchOps = (p: Partial<OperationsFilters>) =>
    setOpsFilters((prev) => ({ ...prev, ...p, offset: 0 }))

  return (
    <div className="p-6 flex flex-col gap-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <Package className="text-accent" size={22} />
          <div>
            <h1 className="text-xl font-semibold text-text-primary">{t('materials.title')}</h1>
            <p className="text-[13px] text-text-muted">{t('materials.subtitle')}</p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => setFormMaterial(null)}>
            <Plus size={15} /> {t('materials.actions.newMaterial')}
          </Button>
          <Button variant="outline" size="sm" onClick={() => setReceiptOpen(true)}>
            <ArrowDownToLine size={15} /> {t('materials.actions.receipt')}
          </Button>
          <Button variant="outline" size="sm" onClick={() => setIssueOpen(true)}>
            <ArrowUpFromLine size={15} /> {t('materials.actions.issue')}
          </Button>
          <Button variant="outline" size="sm" onClick={() => setAdjustmentOpen(true)}>
            <Scale size={15} /> {t('materials.actions.adjustment')}
          </Button>
        </div>
      </div>

      <AccessTabBar
        tabs={[
          { key: 'stock', label: t('materials.tabs.stock') },
          { key: 'operations', label: t('materials.tabs.operations') },
          {
            key: 'procurement',
            label: t('materials.tabs.procurement'),
            badge: procurement.data?.deficit.length || undefined,
          },
        ]}
        active={tab}
        onChange={(key) => setTab(key as Tab)}
      />

      {/* ── Остатки ── */}
      {tab === 'stock' && (
        <>
          <div className="flex flex-wrap items-center gap-3">
            <Input
              className="max-w-xs"
              placeholder={t('materials.stock.search')}
              value={stockQuery}
              onChange={(e) => setStockQuery(e.target.value)}
            />
            <label className="flex items-center gap-2 text-[13px] text-text-secondary">
              <input type="checkbox" checked={onlyLow} onChange={(e) => setOnlyLow(e.target.checked)} />
              {t('materials.stock.onlyLow')}
            </label>
          </div>
          {stock.isLoading ? (
            <LoadingSpinner />
          ) : stock.isError ? (
            <p className="text-[13px] text-red">{t('common.error')}</p>
          ) : (stock.data ?? []).length === 0 ? (
            <div className="bg-bg-card border border-border-default rounded-default overflow-hidden">
              <EmptyState icon="📦" title={t('materials.stock.empty')} />
            </div>
          ) : (
            <div className="overflow-x-auto rounded-default border border-border-default bg-bg-card">
              <table className="w-full border-collapse">
                <thead>
                  <tr className="bg-bg-surface border-b border-border-default">
                    <Th>{t('materials.columns.name')}</Th>
                    <Th>{t('materials.columns.unit')}</Th>
                    <Th>{t('materials.columns.category')}</Th>
                    <Th>{t('materials.columns.stock')}</Th>
                    <Th>{t('materials.columns.stockValue')}</Th>
                    <Th>{t('materials.columns.minStock')}</Th>
                    <Th />
                  </tr>
                </thead>
                <tbody>
                  {(stock.data ?? []).map((row: StockRow) => (
                    <tr key={row.material_id} className="border-b border-border-default last:border-0">
                      <Td>
                        {row.name}
                        {row.low_stock && (
                          <span className="ml-2 rounded-full bg-red/15 text-red text-[11px] px-2 py-0.5">
                            {t('materials.stock.lowBadge')}
                          </span>
                        )}
                      </Td>
                      <Td>{unitLabel(row.unit)}</Td>
                      <Td>{row.category ?? '—'}</Td>
                      <Td className={row.low_stock ? 'text-red font-semibold' : ''}>
                        {fmtQty(row.stock)}
                      </Td>
                      <Td>{fmtMoney(row.stock_value)}</Td>
                      <Td>{row.min_stock !== null ? fmtQty(row.min_stock) : '—'}</Td>
                      <Td>
                        <button
                          className="text-text-muted hover:text-accent cursor-pointer"
                          title={t('common.edit')}
                          onClick={() => {
                            const card = materialById.get(row.material_id)
                            if (card) setFormMaterial(card)
                          }}
                        >
                          <Pencil size={15} />
                        </button>
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      {/* ── Журнал операций ── */}
      {tab === 'operations' && (
        <>
          <div className="flex flex-wrap items-center gap-3">
            <Select
              className="max-w-40"
              value={opsFilters.op_type ?? ''}
              onChange={(e) =>
                patchOps({ op_type: (e.target.value || undefined) as OperationsFilters['op_type'] })
              }
            >
              <option value="">{t('materials.operations.allTypes')}</option>
              <option value="receipt">{t('materials.operations.receipt')}</option>
              <option value="issue">{t('materials.operations.issue')}</option>
            </Select>
            <Select
              className="max-w-56"
              value={opsFilters.material_id ?? ''}
              onChange={(e) =>
                patchOps({ material_id: e.target.value ? Number(e.target.value) : undefined })
              }
            >
              <option value="">{t('materials.operations.allMaterials')}</option>
              {(materials.data ?? []).map((m) => (
                <option key={m.id} value={m.id}>{m.name}</option>
              ))}
            </Select>
            <Input
              className="max-w-40"
              placeholder={t('materials.issue.requestNumber')}
              value={opsFilters.request_number ?? ''}
              onChange={(e) => patchOps({ request_number: e.target.value || undefined })}
            />
            <Input
              className="max-w-40"
              type="date"
              value={opsFilters.date_from ?? ''}
              onChange={(e) => patchOps({ date_from: e.target.value || undefined })}
            />
            <Input
              className="max-w-40"
              type="date"
              value={opsFilters.date_to ?? ''}
              onChange={(e) => patchOps({ date_to: e.target.value || undefined })}
            />
            <Button variant="outline" size="sm" onClick={() => exportOperationsCsv(opsFilters)}>
              <Download size={15} /> CSV
            </Button>
          </div>
          {operations.isLoading ? (
            <LoadingSpinner />
          ) : operations.isError ? (
            <p className="text-[13px] text-red">{t('common.error')}</p>
          ) : (operations.data?.items ?? []).length === 0 ? (
            <div className="bg-bg-card border border-border-default rounded-default overflow-hidden">
              <EmptyState icon="🧾" title={t('materials.operations.empty')} />
            </div>
          ) : (
            <>
              <div className="overflow-x-auto rounded-default border border-border-default bg-bg-card">
                <table className="w-full border-collapse">
                  <thead>
                    <tr className="bg-bg-surface border-b border-border-default">
                      <Th>{t('materials.columns.date')}</Th>
                      <Th>{t('materials.columns.opType')}</Th>
                      <Th>{t('materials.columns.name')}</Th>
                      <Th>{t('materials.columns.qty')}</Th>
                      <Th>{t('materials.columns.amount')}</Th>
                      <Th>{t('materials.columns.request')}</Th>
                      <Th>{t('materials.columns.detail')}</Th>
                      <Th />
                    </tr>
                  </thead>
                  <tbody>
                    {(operations.data?.items ?? []).map((op) => (
                      <tr key={`${op.op_type}-${op.id}`} className="border-b border-border-default last:border-0">
                        <Td className="whitespace-nowrap">
                          {op.created_at ? new Date(op.created_at).toLocaleString('ru-RU') : '—'}
                        </Td>
                        <Td>
                          <span className={op.op_type === 'receipt' ? 'text-green' : 'text-orange'}>
                            {t(`materials.opType.${op.op_type}`)}
                          </span>
                          <span className="text-text-muted text-[11px]"> · {t(`materials.docType.${op.doc_type}`)}</span>
                        </Td>
                        <Td>{op.material_name}</Td>
                        <Td>{fmtQty(op.qty)} {unitLabel(op.unit)}</Td>
                        <Td>{fmtMoney(op.amount)}</Td>
                        <Td>{op.request_number ?? '—'}</Td>
                        <Td className="max-w-56 truncate" >
                          {op.supplier ?? op.reason ?? '—'}
                        </Td>
                        <Td>
                          {(op.doc_type === 'purchase' || op.doc_type === 'request' || op.doc_type === 'household') && (
                            <button
                              className="text-text-muted hover:text-red cursor-pointer"
                              title={t('materials.reversal.action')}
                              onClick={() => setReversalOp(op)}
                            >
                              <Undo2 size={15} />
                            </button>
                          )}
                        </Td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <AccessPagination
                total={operations.data?.total ?? 0}
                limit={opsFilters.limit ?? PAGE_LIMIT}
                offset={opsFilters.offset ?? 0}
                onOffsetChange={(offset) => setOpsFilters((prev) => ({ ...prev, offset }))}
              />
            </>
          )}
        </>
      )}

      {/* ── На закуп ── */}
      {tab === 'procurement' && (
        <>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={() => exportProcurementCsv()}>
              <Download size={15} /> CSV
            </Button>
          </div>
          {procurement.isLoading ? (
            <LoadingSpinner />
          ) : procurement.isError ? (
            <p className="text-[13px] text-red">{t('common.error')}</p>
          ) : (
            <>
              {(procurement.data?.deficit ?? []).length === 0 ? (
                <div className="bg-bg-card border border-border-default rounded-default overflow-hidden">
                  <EmptyState icon="✅" title={t('materials.procurement.empty')} />
                </div>
              ) : (
                <div className="overflow-x-auto rounded-default border border-border-default bg-bg-card">
                  <table className="w-full border-collapse">
                    <thead>
                      <tr className="bg-bg-surface border-b border-border-default">
                        <Th>{t('materials.columns.name')}</Th>
                        <Th>{t('materials.columns.unit')}</Th>
                        <Th>{t('materials.columns.stock')}</Th>
                        <Th>{t('materials.columns.minStock')}</Th>
                        <Th>{t('materials.columns.toBuy')}</Th>
                      </tr>
                    </thead>
                    <tbody>
                      {(procurement.data?.deficit ?? []).map((row) => (
                        <tr key={row.material_id} className="border-b border-border-default last:border-0">
                          <Td>{row.name}</Td>
                          <Td>{unitLabel(row.unit)}</Td>
                          <Td className="text-red font-semibold">{fmtQty(row.stock)}</Td>
                          <Td>{fmtQty(row.min_stock)}</Td>
                          <Td className="font-semibold">{fmtQty(row.to_buy)}</Td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {(procurement.data?.open_purchase_requests ?? []).length > 0 && (
                <div className="flex flex-col gap-2">
                  <h2 className="text-[15px] font-semibold text-text-primary">
                    {t('materials.procurement.openRequests')}
                  </h2>
                  <div className="flex flex-col gap-2">
                    {(procurement.data?.open_purchase_requests ?? []).map((req) => (
                      <div
                        key={req.request_number}
                        className="bg-bg-card border border-border-default rounded-default p-3 text-[13px]"
                      >
                        <div className="flex items-center gap-2">
                          {/* deep-link читает KanbanPage (?request=) — открывает карточку */}
                          <Link
                            to={`/dashboard?request=${req.request_number}`}
                            className="font-semibold text-accent hover:underline"
                          >
                            №{req.request_number}
                          </Link>
                          {req.executor_name && (
                            <span className="text-text-muted">{req.executor_name}</span>
                          )}
                        </div>
                        <p className="text-text-secondary whitespace-pre-wrap">
                          {req.requested_materials ?? '—'}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}
        </>
      )}

      <MaterialFormDialog
        open={formMaterial !== undefined}
        material={formMaterial ?? null}
        onClose={() => setFormMaterial(undefined)}
      />
      <ReceiptDialog open={receiptOpen} onClose={() => setReceiptOpen(false)} />
      <IssueDialog open={issueOpen} onClose={() => setIssueOpen(false)} />
      <AdjustmentDialog open={adjustmentOpen} onClose={() => setAdjustmentOpen(false)} />
      <ReversalDialog operation={reversalOp} onClose={() => setReversalOp(null)} />
    </div>
  )
}
