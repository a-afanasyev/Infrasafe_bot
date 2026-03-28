import { useState, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { useBulkCreateApartments } from '../../hooks/useAddresses'
import type { BulkCreateResult } from '../../types/api'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { Button } from '@/components/ui/button'

// -- Parsing ------------------------------------------------------------------

function parseApartmentRange(input: string): string[] {
  const parts = input.split(',').map(s => s.trim()).filter(Boolean)
  const numbers = new Set<string>()
  for (const part of parts) {
    const rangeMatch = part.match(/^(\d+)\s*-\s*(\d+)$/)
    if (rangeMatch) {
      const start = parseInt(rangeMatch[1], 10)
      const end = parseInt(rangeMatch[2], 10)
      if (start <= end && end - start < 500) {
        for (let i = start; i <= end; i++) {
          numbers.add(String(i))
        }
      }
    } else if (part) {
      numbers.add(part)
    }
  }
  return Array.from(numbers).sort((a, b) => {
    const na = parseInt(a, 10)
    const nb = parseInt(b, 10)
    if (!isNaN(na) && !isNaN(nb)) return na - nb
    return a.localeCompare(b)
  })
}

// -- Component ----------------------------------------------------------------

interface Props {
  buildingId: number
  buildingAddress: string
  onClose: () => void
}

export default function BulkCreateModal({ buildingId, buildingAddress, onClose }: Props) {
  const { t } = useTranslation()
  const [input, setInput] = useState('')
  const [result, setResult] = useState<BulkCreateResult | null>(null)

  const bulkCreate = useBulkCreateApartments()

  const parsed = useMemo(() => parseApartmentRange(input), [input])
  const tooMany = parsed.length > 500

  const canSubmit = parsed.length > 0 && !tooMany && !bulkCreate.isPending

  const handleSubmit = () => {
    if (!canSubmit) return
    bulkCreate.mutate(
      { building_id: buildingId, apartment_numbers: parsed },
      { onSuccess: (data) => setResult(data) },
    )
  }

  return (
    <Dialog open onOpenChange={(open) => { if (!open) onClose() }}>
      <DialogContent className="max-w-[480px]">
        <DialogHeader>
          <DialogTitle>{t('addressForms.bulkTitle')}</DialogTitle>
        </DialogHeader>

        <div className="flex flex-col gap-4">
          <div className="text-[13px] text-text-secondary font-[family-name:var(--font-display)]">
            {buildingAddress}
          </div>

          {result ? (
            /* Result summary */
            <div className="p-4 bg-bg-surface rounded-sm border border-border-default flex flex-col gap-1.5 font-[family-name:var(--font-display)] text-sm text-text-primary">
              <div>{t('addressForms.resultCreated', { count: result.created })}</div>
              <div>{t('addressForms.resultSkipped', { count: result.skipped })}</div>
              {result.errors.length > 0 && (
                <div className="text-red">
                  {t('addressForms.resultErrors', { errors: result.errors.join(', ') })}
                </div>
              )}
            </div>
          ) : (
            /* Input form */
            <>
              <div>
                <Label className="mb-1 block text-xs text-text-muted">{t('addressForms.aptNumbers')}</Label>
                <Textarea
                  value={input}
                  onChange={e => setInput(e.target.value)}
                  placeholder={t('addressForms.aptPlaceholder')}
                  className="min-h-[80px]"
                  autoFocus
                />
              </div>

              {input.trim() && (
                <div className={`text-[13px] font-[family-name:var(--font-display)] ${tooMany ? 'text-red' : 'text-text-secondary'}`}>
                  {tooMany
                    ? t('addressForms.tooMany')
                    : t('addressForms.willCreate', { count: parsed.length })
                  }
                </div>
              )}

              {bulkCreate.error && (
                <div className="text-red text-[13px] font-[family-name:var(--font-display)]">
                  {(bulkCreate.error as any)?.response?.data?.detail || (bulkCreate.error as Error).message || t('addressForms.createError')}
                </div>
              )}
            </>
          )}
        </div>

        <DialogFooter>
          {result ? (
            <Button onClick={onClose}>OK</Button>
          ) : (
            <>
              <Button variant="outline" onClick={onClose}>{t('common.cancel')}</Button>
              <Button
                onClick={handleSubmit}
                disabled={!canSubmit}
              >
                {bulkCreate.isPending ? t('common.creating') : t('common.create')}
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
