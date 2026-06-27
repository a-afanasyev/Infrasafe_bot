import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { FlaskConical } from 'lucide-react'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select } from '@/components/ui/select'
import { DecisionBadge } from './AccessBadges'
import { useTestControllerEvent } from '../../hooks/useAccessEquipment'
import type { ControllerRow, GateDirection, TestEventPayload, TestEventResponse, ZoneRow, GateRow } from '../../types/access'

/**
 * Диалог диагностики точки въезда (только system_admin). Прогоняет синтетический
 * ANPR-проезд через Decision Engine (POST /admin/controllers/{id}/test-event):
 * параметры (номер/направление/уверенность) → результат (решение, причина,
 * команда шлагбауму) показывается в том же окне. Тест можно повторить.
 *
 * Дефолты совпадают с бэкендом: plate_number=DIAG0001, direction=entry,
 * confidence=0.99 — оператору достаточно нажать «Запустить».
 */
interface Props {
  /** Контроллер для теста. null → диалог закрыт. */
  controller: ControllerRow | null
  /** Источники подписей зоны/въезда (для человекочитаемого результата). */
  zones: ZoneRow[]
  gates: GateRow[]
  onClose: () => void
}

const DEFAULT_PLATE = 'DIAG0001'
const DEFAULT_CONFIDENCE = '0.99'

function ResultRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-3 text-[13px]">
      <span className="text-text-muted">{label}</span>
      <span className="text-right font-medium text-text-primary">{value}</span>
    </div>
  )
}

export default function ControllerTestDialog({ controller, zones, gates, onClose }: Props) {
  const { t } = useTranslation()
  const test = useTestControllerEvent()
  const open = controller !== null

  const [plate, setPlate] = useState(DEFAULT_PLATE)
  const [direction, setDirection] = useState<GateDirection>('entry')
  const [confidence, setConfidence] = useState(DEFAULT_CONFIDENCE)
  const [result, setResult] = useState<TestEventResponse | null>(null)

  // Сброс при открытии (render-time, как в EquipmentFormDialog).
  const [prevOpen, setPrevOpen] = useState(false)
  if (open !== prevOpen) {
    setPrevOpen(open)
    if (open) {
      setPlate(DEFAULT_PLATE)
      setDirection('entry')
      setConfidence(DEFAULT_CONFIDENCE)
      setResult(null)
    }
  }

  const zoneLabel = (id: number | null) => {
    if (id == null) return '—'
    const z = zones.find((z) => z.id === id)
    return z ? `${z.code} — ${z.name}` : `#${id}`
  }
  const gateLabel = (id: number | null) => {
    if (id == null) return '—'
    const g = gates.find((g) => g.id === id)
    return g ? g.code : `#${id}`
  }

  function run() {
    if (!controller) return
    const payload: TestEventPayload = { direction }
    const p = plate.trim()
    if (p) payload.plate_number = p
    const c = Number(confidence)
    if (confidence.trim() && Number.isFinite(c)) payload.confidence = c
    test.mutate({ id: controller.id, payload }, { onSuccess: (res) => setResult(res) })
  }

  const directions: GateDirection[] = ['entry', 'exit']

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <FlaskConical size={18} className="text-accent" />
            {t('accessControl.equipment.test.title')}
          </DialogTitle>
          <DialogDescription>
            {t('accessControl.equipment.test.subtitle', { uid: controller?.controller_uid ?? '' })}
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-3">
          <p className="text-[12px] text-text-muted">{t('accessControl.equipment.test.desc')}</p>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="test-plate">{t('accessControl.equipment.test.plateLabel')}</Label>
            <Input
              id="test-plate"
              value={plate}
              onChange={(e) => setPlate(e.target.value)}
              placeholder={DEFAULT_PLATE}
              className="font-mono"
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="test-direction">{t('accessControl.equipment.test.directionLabel')}</Label>
            <Select
              id="test-direction"
              value={direction}
              onChange={(e) => setDirection(e.target.value as GateDirection)}
            >
              {directions.map((d) => (
                <option key={d} value={d}>
                  {t(`accessControl.direction.${d}`)}
                </option>
              ))}
            </Select>
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="test-confidence">{t('accessControl.equipment.test.confidenceLabel')}</Label>
            <Input
              id="test-confidence"
              type="number"
              min={0}
              max={1}
              step={0.01}
              value={confidence}
              onChange={(e) => setConfidence(e.target.value)}
              placeholder={DEFAULT_CONFIDENCE}
            />
          </div>

          {result && (
            <div className="flex flex-col gap-2 rounded-default border border-border-default bg-bg-surface p-3">
              <div className="flex items-center justify-between gap-3">
                <span className="text-[12px] font-bold uppercase tracking-wider text-text-muted">
                  {t('accessControl.equipment.test.resultTitle')}
                </span>
                <DecisionBadge decision={result.decision} />
              </div>
              <ResultRow
                label={t('accessControl.columns.reason')}
                value={result.reason ? t(`accessControl.reason.${result.reason}`, { defaultValue: result.reason }) : '—'}
              />
              <ResultRow label={t('accessControl.equipment.test.decisionId')} value={result.decision_id ?? '—'} />
              <ResultRow
                label={t('accessControl.equipment.test.eventId')}
                value={<span className="font-mono">{result.event_id}</span>}
              />
              <ResultRow label={t('accessControl.equipment.test.zone')} value={zoneLabel(result.zone_id)} />
              <ResultRow label={t('accessControl.equipment.test.gate')} value={gateLabel(result.gate_id)} />
              <ResultRow
                label={t('accessControl.equipment.test.barrier')}
                value={result.barrier_id != null ? `#${result.barrier_id}` : '—'}
              />
              <ResultRow
                label={t('accessControl.equipment.test.command')}
                value={
                  result.command
                    ? t('accessControl.equipment.test.commandCreated', { id: result.command.command_id })
                    : t('accessControl.equipment.test.noCommand')
                }
              />
              <p className="mt-1 text-[12px] text-text-muted">{t('accessControl.equipment.test.hint')}</p>
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={test.isPending}>
            {t('common.close')}
          </Button>
          <Button onClick={run} disabled={test.isPending}>
            {test.isPending
              ? t('accessControl.equipment.test.running')
              : result
                ? t('accessControl.equipment.test.rerun')
                : t('accessControl.equipment.test.run')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
