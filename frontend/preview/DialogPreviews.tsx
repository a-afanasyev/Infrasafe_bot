import { useTranslation } from 'react-i18next'
import { KeyRound, AlertTriangle, Copy, FlaskConical } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Select } from '@/components/ui/select'
import { DecisionBadge } from '@/components/access/AccessBadges'
import { testResult, demoApiKey } from './mockData'

/**
 * Инлайновые превью диалогов действий (для скриншотов). Реальные диалоги —
 * Radix-портал с `fixed inset-0` оверлеем во весь экран: их нельзя показать
 * «рядом» в одном кадре. Поэтому здесь — тонкие копии ТЕЛА диалогов (как
 * LiveFeedPreview для WS-ленты): та же разметка/классы/i18n-ключи, что в
 * боевых компонентах, но в виде карточек на странице. Обработчики — no-op.
 */

// Оболочка «как DialogContent» (рамка/паддинги/радиус карточки диалога).
function DialogCard({
  title,
  description,
  titleIcon,
  children,
  footer,
}: {
  title: string
  description?: string
  titleIcon?: React.ReactNode
  children?: React.ReactNode
  footer: React.ReactNode
}) {
  return (
    <div className="grid w-full max-w-md gap-4 rounded-default border border-border-default bg-bg-card p-6 shadow-lg">
      <div className="flex flex-col space-y-1.5">
        <h3 className="flex items-center gap-2 text-lg font-semibold leading-none tracking-tight text-text-primary">
          {titleIcon}
          {title}
        </h3>
        {description && <p className="text-sm text-text-muted">{description}</p>}
      </div>
      {children}
      <div className="flex flex-row justify-end gap-2">{footer}</div>
    </div>
  )
}

// ── (1) VehicleStatusDialog — блокировка авто с причиной ──────────────────────
function VehicleStatusBlockPreview() {
  const { t } = useTranslation()
  return (
    <DialogCard
      title={t('accessControl.statusDialog.blockTitle')}
      description={t('accessControl.statusDialog.blockDesc', { plate: '85C456EF' })}
      footer={
        <>
          <Button variant="outline">{t('common.cancel')}</Button>
          <Button variant="destructive">{t('accessControl.actions.block')}</Button>
        </>
      }
    >
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="prev-block-reason">{t('accessControl.statusDialog.reasonLabel')}</Label>
        <Textarea
          id="prev-block-reason"
          rows={3}
          defaultValue="Долг по парковке за 2 месяца"
          placeholder={t('accessControl.statusDialog.reasonPlaceholder')}
        />
      </div>
    </DialogCard>
  )
}

// ── (2) TaxiPassFormDialog — создание taxi-пропуска ──────────────────────────
function TaxiPassFormPreview() {
  const { t } = useTranslation()
  return (
    <DialogCard
      title={t('accessControl.taxiPassForm.title')}
      description={t('accessControl.taxiPassForm.desc')}
      footer={
        <>
          <Button variant="outline">{t('common.cancel')}</Button>
          <Button>{t('accessControl.taxiPassForm.submit')}</Button>
        </>
      }
    >
      <div className="flex flex-col gap-3">
        <div className="grid grid-cols-2 gap-3">
          <div className="flex flex-col gap-1.5">
            <Label>{t('accessControl.taxiPassForm.apartmentId')}</Label>
            <Input type="number" defaultValue="12" />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label>{t('accessControl.taxiPassForm.zoneId')}</Label>
            <Input type="number" defaultValue="1" />
          </div>
        </div>
        <div className="flex flex-col gap-1.5">
          <Label>{t('accessControl.taxiPassForm.plate')}</Label>
          <Input className="font-mono" defaultValue="10D908GH" placeholder={t('accessControl.taxiPassForm.platePlaceholder')} />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div className="flex flex-col gap-1.5">
            <Label>{t('accessControl.taxiPassForm.validFrom')}</Label>
            <Input type="datetime-local" />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label>{t('accessControl.taxiPassForm.validUntil')}</Label>
            <Input type="datetime-local" />
          </div>
        </div>
        <div className="flex flex-col gap-1.5">
          <Label>{t('accessControl.taxiPassForm.maxEntries')}</Label>
          <Input type="number" min={1} defaultValue="2" />
        </div>
      </div>
    </DialogCard>
  )
}

// ── (3) RequestReviewDialog — подтверждение заявки жителя ─────────────────────
function RequestReviewApprovePreview() {
  const { t } = useTranslation()
  return (
    <DialogCard
      title={t('accessControl.reviewDialog.approveTitle')}
      description={t('accessControl.reviewDialog.approveDesc', { plate: '50E222JK' })}
      footer={
        <>
          <Button variant="outline">{t('common.cancel')}</Button>
          <Button>{t('accessControl.actions.approve')}</Button>
        </>
      }
    >
      <div className="flex flex-col gap-3">
        <div className="flex flex-col gap-1.5">
          <Label>{t('accessControl.reviewDialog.zoneLabel')}</Label>
          <Input type="number" defaultValue="1" placeholder={t('accessControl.reviewDialog.zonePlaceholder')} />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label>{t('accessControl.reviewDialog.commentLabel')}</Label>
          <Textarea rows={3} defaultValue="Документы подтверждены" placeholder={t('accessControl.reviewDialog.commentPlaceholder')} />
        </div>
      </div>
    </DialogCard>
  )
}

// ── (4) ControllerKeyDialog — показ API-ключа (один раз) ──────────────────────
function ControllerKeyPreview() {
  const { t } = useTranslation()
  return (
    <DialogCard
      title={t('accessControl.equipment.key.title')}
      titleIcon={<KeyRound size={18} className="text-accent" />}
      description={t('accessControl.equipment.key.subtitle', { uid: 'ctrl-main-01' })}
      footer={<Button>{t('accessControl.equipment.key.done')}</Button>}
    >
      <div className="flex flex-col gap-3">
        <div className="flex items-start gap-2 rounded-default border border-amber-300 bg-amber-50 p-3 text-[12px] text-amber-800 dark:border-amber-900/50 dark:bg-amber-900/20 dark:text-amber-300">
          <AlertTriangle size={16} className="mt-0.5 shrink-0" />
          <span>{t('accessControl.equipment.key.warning')}</span>
        </div>
        <div className="flex items-center gap-2">
          <code className="flex-1 overflow-x-auto rounded-sm border border-border-default bg-bg-surface px-3 py-2 font-mono text-[13px] text-text-primary">
            {demoApiKey}
          </code>
          <Button variant="outline" size="icon" aria-label={t('accessControl.equipment.key.copy')}>
            <Copy size={16} />
          </Button>
        </div>
      </div>
    </DialogCard>
  )
}

// ── (5) ControllerTestDialog — тест точки въезда с РЕЗУЛЬТАТОМ ────────────────
function ResultRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-3 text-[13px]">
      <span className="text-text-muted">{label}</span>
      <span className="text-right font-medium text-text-primary">{value}</span>
    </div>
  )
}

function ControllerTestPreview() {
  const { t } = useTranslation()
  const r = testResult
  return (
    <DialogCard
      title={t('accessControl.equipment.test.title')}
      titleIcon={<FlaskConical size={18} className="text-accent" />}
      description={t('accessControl.equipment.test.subtitle', { uid: 'ctrl-main-01' })}
      footer={
        <>
          <Button variant="outline">{t('common.close')}</Button>
          <Button>{t('accessControl.equipment.test.rerun')}</Button>
        </>
      }
    >
      <div className="flex flex-col gap-3">
        <p className="text-[12px] text-text-muted">{t('accessControl.equipment.test.desc')}</p>
        <div className="flex flex-col gap-1.5">
          <Label>{t('accessControl.equipment.test.plateLabel')}</Label>
          <Input className="font-mono" defaultValue="DIAG0001" />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label>{t('accessControl.equipment.test.directionLabel')}</Label>
          <Select defaultValue="entry">
            <option value="entry">{t('accessControl.direction.entry')}</option>
            <option value="exit">{t('accessControl.direction.exit')}</option>
          </Select>
        </div>
        <div className="flex flex-col gap-1.5">
          <Label>{t('accessControl.equipment.test.confidenceLabel')}</Label>
          <Input type="number" min={0} max={1} step={0.01} defaultValue="0.99" />
        </div>

        <div className="flex flex-col gap-2 rounded-default border border-border-default bg-bg-surface p-3">
          <div className="flex items-center justify-between gap-3">
            <span className="text-[12px] font-bold uppercase tracking-wider text-text-muted">
              {t('accessControl.equipment.test.resultTitle')}
            </span>
            <DecisionBadge decision={r.decision} />
          </div>
          <ResultRow
            label={t('accessControl.columns.reason')}
            value={t(`accessControl.reason.${r.reason}`, { defaultValue: r.reason ?? '—' })}
          />
          <ResultRow label={t('accessControl.equipment.test.decisionId')} value={r.decision_id ?? '—'} />
          <ResultRow label={t('accessControl.equipment.test.eventId')} value={<span className="font-mono">{r.event_id}</span>} />
          <ResultRow label={t('accessControl.equipment.test.zone')} value="Z-MAIN — Главный двор" />
          <ResultRow label={t('accessControl.equipment.test.gate')} value="G-MAIN-IN" />
          <ResultRow label={t('accessControl.equipment.test.barrier')} value={r.barrier_id != null ? `#${r.barrier_id}` : '—'} />
          <ResultRow
            label={t('accessControl.equipment.test.command')}
            value={
              r.command
                ? t('accessControl.equipment.test.commandCreated', { id: r.command.command_id })
                : t('accessControl.equipment.test.noCommand')
            }
          />
          <p className="mt-1 text-[12px] text-text-muted">{t('accessControl.equipment.test.hint')}</p>
        </div>
      </div>
    </DialogCard>
  )
}

export {
  VehicleStatusBlockPreview,
  TaxiPassFormPreview,
  RequestReviewApprovePreview,
  ControllerKeyPreview,
  ControllerTestPreview,
}
