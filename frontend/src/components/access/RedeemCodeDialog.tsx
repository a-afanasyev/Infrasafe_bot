import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import axios from 'axios'
import { CheckCircle2, KeyRound } from 'lucide-react'
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
import { useRedeemGuestCode } from '../../hooks/useAccessRegistry'
import type { RedeemCodeResponse } from '../../types/access'

/**
 * Диалог проверки одноразового гостевого кода оператором (§9.3).
 *
 * Поток: оператор вводит 8-значный код (моноширинный) → «Проверить» →
 *  - успех (200): раскрываем КВАРТИРУ + тип пропуска + «шлагбаум открыт»
 *    (command_id) — оператор пускает гостя;
 *  - 422 (code_invalid): общий текст «Код неверный или недействителен» —
 *    деталь не раскрываем;
 *  - 429 (too_many_attempts): «Слишком много попыток, попробуйте позже».
 *
 * Гейтинг — на уровне роута (/dashboard/access гейтится ACCESS_MODULE_ROLES,
 * что совпадает с RBAC redeem-эндпоинта: security_operator/manager/system_admin).
 */

const CODE_LENGTH = 8

type ErrorKind = 'invalid' | 'blocked' | 'generic'

interface Props {
  open: boolean
  onClose: () => void
}

export default function RedeemCodeDialog({ open, onClose }: Props) {
  const { t } = useTranslation()
  const redeem = useRedeemGuestCode()
  const [code, setCode] = useState('')
  const [result, setResult] = useState<RedeemCodeResponse | null>(null)
  const [errorKind, setErrorKind] = useState<ErrorKind | null>(null)

  // Сброс полей при открытии (render-time pattern, как в ResolveDialog): иначе
  // прошлый результат/ошибка «перетекали» бы в новую проверку.
  const [prevOpen, setPrevOpen] = useState(false)
  if (open !== prevOpen) {
    setPrevOpen(open)
    if (open) {
      setCode('')
      setResult(null)
      setErrorKind(null)
      redeem.reset()
    }
  }

  const canSubmit = code.length === CODE_LENGTH && !redeem.isPending

  function handleSubmit() {
    if (!canSubmit) return
    setResult(null)
    setErrorKind(null)
    redeem.mutate(
      { code },
      {
        onSuccess: (data) => setResult(data),
        onError: (err) => {
          const status = axios.isAxiosError(err) ? err.response?.status : undefined
          setErrorKind(status === 429 ? 'blocked' : status === 422 ? 'invalid' : 'generic')
        },
      },
    )
  }

  function resetForRetry() {
    setCode('')
    setResult(null)
    setErrorKind(null)
    redeem.reset()
  }

  const errorText =
    errorKind === 'blocked'
      ? t('accessControl.redeem.errorBlocked')
      : errorKind === 'invalid'
        ? t('accessControl.redeem.errorInvalid')
        : errorKind === 'generic'
          ? t('accessControl.redeem.errorGeneric')
          : null

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <KeyRound size={18} className="text-accent" />
            {t('accessControl.redeem.title')}
          </DialogTitle>
          <DialogDescription>{t('accessControl.redeem.desc')}</DialogDescription>
        </DialogHeader>

        {result ? (
          // ── Раскрытие после успеха (§9.3) ──────────────────────────────────
          <div className="flex flex-col gap-3" data-testid="redeem-result">
            <div className="flex items-center gap-2 text-emerald-600 dark:text-emerald-400">
              <CheckCircle2 size={20} />
              <span className="text-[15px] font-semibold">
                {t('accessControl.redeem.barrierOpened')}
              </span>
            </div>
            <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-[14px]">
              <dt className="text-text-muted">{t('accessControl.redeem.apartment')}</dt>
              <dd className="font-semibold text-text-primary">{result.apartment_id}</dd>
              <dt className="text-text-muted">{t('accessControl.redeem.passType')}</dt>
              <dd className="text-text-primary">
                {t(`accessControl.passes.passType.${result.pass_type}`, {
                  defaultValue: result.pass_type,
                })}
              </dd>
              <dt className="text-text-muted">{t('accessControl.redeem.commandId')}</dt>
              <dd className="font-mono text-[13px] text-text-muted break-all">
                {result.command.command_id}
              </dd>
            </dl>
          </div>
        ) : (
          <div className="flex flex-col gap-3">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="redeem-code">{t('accessControl.redeem.codeLabel')}</Label>
              <Input
                id="redeem-code"
                inputMode="numeric"
                autoComplete="off"
                value={code}
                onChange={(e) => setCode(e.target.value.replace(/\D/g, '').slice(0, CODE_LENGTH))}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleSubmit()
                }}
                placeholder={t('accessControl.redeem.codePlaceholder')}
                className="font-mono text-center text-lg tracking-[0.4em]"
              />
            </div>
            {errorText && (
              <p className="text-[13px] text-red" role="alert">
                {errorText}
              </p>
            )}
          </div>
        )}

        <DialogFooter>
          {result ? (
            <>
              <Button variant="outline" onClick={resetForRetry}>
                {t('accessControl.redeem.checkAnother')}
              </Button>
              <Button onClick={onClose}>{t('common.close')}</Button>
            </>
          ) : (
            <>
              <Button variant="outline" onClick={onClose} disabled={redeem.isPending}>
                {t('common.cancel')}
              </Button>
              <Button disabled={!canSubmit} onClick={handleSubmit}>
                {t('accessControl.redeem.check')}
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
