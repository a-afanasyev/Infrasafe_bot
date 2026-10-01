import { useTranslation } from 'react-i18next'

// FE-119: format the InfraSafe working-range band. One-sided when only min OR
// max is present (e.g. heating ≥40 °C, transformer load ≤80 %).
function formatWorkingRange(
  min?: number | null,
  max?: number | null,
  unit?: string | null,
): string | null {
  const u = unit ? ` ${unit}` : ''
  if (min != null && max != null) return `${min}–${max}${u}`
  if (min != null) return `≥ ${min}${u}`
  if (max != null) return `≤ ${max}${u}`
  return null
}

interface AlertContextRequest {
  reopen_sequence?: number | null
  related_request_number?: string | null
  engineer_required_reason?: string | null
  metric_label?: string | null
  metric_value?: number | string | null
  metric_unit?: string | null
  metric_normal_min?: number | null
  metric_normal_max?: number | null
  infrastructure_label?: string | null
}

/**
 * Контекст заявки из inbound-алерта InfraSafe: цепочка переоткрытий (INT-120 #4)
 * и метрика/объект (FE-119). Для ручных заявок ничего не рендерит.
 */
export default function RequestAlertContext({
  request,
  onOpenRelated,
}: {
  request: AlertContextRequest
  onOpenRelated?: (relatedRequestNumber: string) => void
}) {
  const { t } = useTranslation()
  return (
    <>
      {/* INT-120 #4 — Sprint 10 reopen-chain context.
          Backend surfaces these from webhook_inbox.payload.alert when
          the request was created via inbound InfraSafe alert (sub-task
          #3). reopen_sequence is null for first-time alerts and
          manual requests; engineer_required_reason is non-null only
          on alert.engineer_required chain-end transitions. */}
      {(request.reopen_sequence || request.engineer_required_reason) && (
        <div className="bg-amber/8 border border-amber/25 rounded-[10px] px-3 py-2.5 text-[13px] flex flex-col gap-1.5">
          {request.reopen_sequence && (
            <div className="flex items-center gap-1.5 flex-wrap">
              <span className="font-semibold text-[#d97706]">
                🔁 {t('kanban.reopenBadge', { n: request.reopen_sequence })}
              </span>
              {request.related_request_number && (
                <>
                  <span className="text-text-muted">·</span>
                  <span className="text-text-secondary">
                    {t('kanban.relatedRequest')}{' '}
                  </span>
                  {onOpenRelated ? (
                    <button
                      type="button"
                      onClick={() => onOpenRelated(request.related_request_number as string)}
                      className="font-[family-name:var(--font-mono)] text-blue hover:underline cursor-pointer"
                    >
                      {request.related_request_number}
                    </button>
                  ) : (
                    <span className="font-[family-name:var(--font-mono)] text-text-primary">
                      {request.related_request_number}
                    </span>
                  )}
                </>
              )}
            </div>
          )}
          {request.engineer_required_reason && (
            <div className="flex items-center gap-1.5 flex-wrap pt-1 border-t border-amber/15">
              <span className="font-semibold text-red">
                ⚠ {t('kanban.engineerEscalation')}
              </span>
              <span className="text-text-secondary">
                {t('kanban.engineerReason')}{' '}
              </span>
              <span className="font-[family-name:var(--font-mono)] text-text-primary text-[12px]">
                {request.engineer_required_reason}
              </span>
            </div>
          )}
        </div>
      )}

      {/* FE-119 — InfraSafe alert context (metric + infrastructure).
          Rendered only for requests created from an inbound alert.
          metric_value absent → label-only (e.g. LEAK_DETECTED). */}
      {(request.metric_label || request.infrastructure_label) && (
        <div className="bg-blue/8 border border-blue/25 rounded-[10px] px-3 py-2.5 text-[13px] flex flex-col gap-1">
          <span className="font-semibold text-blue text-[11px] uppercase tracking-wide font-[family-name:var(--font-display)]">
            📡 {t('kanban.alertSource')}
          </span>
          {request.infrastructure_label && (
            <div className="text-text-secondary">{request.infrastructure_label}</div>
          )}
          {request.metric_label && (
            <div className="text-text-primary">
              {request.metric_label}
              {request.metric_value != null && (
                <>
                  {': '}
                  <span className="font-[family-name:var(--font-mono)] font-semibold">
                    {request.metric_value}{request.metric_unit ? ` ${request.metric_unit}` : ''}
                  </span>
                  {formatWorkingRange(request.metric_normal_min, request.metric_normal_max, request.metric_unit) && (
                    <span className="text-text-muted">
                      {' '}({t('kanban.workingRange')} {formatWorkingRange(request.metric_normal_min, request.metric_normal_max, request.metric_unit)})
                    </span>
                  )}
                </>
              )}
            </div>
          )}
        </div>
      )}
    </>
  )
}
