import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Input } from '@/components/ui/input'
import { useCreateInvite } from '@/hooks/useEmployees'
import { getSpecDisplay } from '@/utils/employeeUtils'
import { cn } from '@/lib/utils'
import { toast } from 'sonner'

interface Props {
  open: boolean
  onClose: () => void
}

const SPEC_KEYS = ['electrician', 'plumber', 'heating', 'cleaning', 'security', 'elevator', 'landscaping', 'ventilation']

export default function AddEmployeeModal({ open, onClose }: Props) {
  const { t } = useTranslation()

  const EXPIRY_OPTIONS = [
    { value: 1, label: t('employeeModal.expiry1h', '1 час') },
    { value: 24, label: t('employeeModal.expiry24h', '24 часа') },
    { value: 168, label: t('employeeModal.expiry7d', '7 дней') },
  ]
  // Form state — только то, что несёт инвайт-токен (роль/спец/срок). ФИО и
  // телефон кандидат вводит сам при регистрации в боте.
  const [role, setRole] = useState<'executor' | 'manager'>('executor')
  const [specs, setSpecs] = useState<string[]>([])
  const [invHours, setInvHours] = useState(24)

  // Result state — after invite generation
  const [inviteResult, setInviteResult] = useState<{
    token: string
    bot_link: string
    expires_at: string
  } | null>(null)

  const createInvite = useCreateInvite()

  function reset() {
    setRole('executor')
    setSpecs([])
    setInvHours(24)
    setInviteResult(null)
  }

  function handleClose() {
    reset()
    onClose()
  }

  function toggleSpec(key: string) {
    setSpecs(prev => prev.includes(key) ? prev.filter(s => s !== key) : [...prev, key])
  }

  function handleCreate() {
    const specsList = role === 'executor' ? specs : []
    // Только инвайт: реальная запись сотрудника создаётся при входе по боту
    // (реальный telegram_id + applicant + роль), без плейсхолдеров-дублей.
    createInvite.mutate(
      { role, specializations: specsList, hours: invHours },
      { onSuccess: (data) => setInviteResult(data) },
    )
  }

  async function copyToClipboard(text: string) {
    try {
      await navigator.clipboard.writeText(text)
      toast.success(t('employeeModal.inviteCopied'))
    } catch {
      toast.error(t('employeeModal.copyFailed'))
    }
  }

  const isPending = createInvite.isPending

  return (
    <Dialog open={open} onOpenChange={(v) => !v && handleClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{t('employeeModal.titleInvite', 'Пригласить сотрудника')}</DialogTitle>
          <DialogDescription>
            {inviteResult
              ? t('employeeModal.createdDesc')
              : t('employeeModal.inviteFormDesc', 'Выберите роль и срок действия — бот выдаст ссылку-приглашение.')}
          </DialogDescription>
        </DialogHeader>

        {/* ===== Form ===== */}
        {!inviteResult && (
          <div className="flex flex-col gap-3">
            <div className="flex flex-col gap-1.5">
              <Label>{t('employeeModal.role')}</Label>
              <div className="flex gap-2">
                {([
                  { value: 'executor' as const, label: t('role.executor') },
                  { value: 'manager' as const, label: t('role.manager') },
                ]).map(r => (
                  <button
                    key={r.value}
                    onClick={() => setRole(r.value)}
                    className={cn(
                      'px-3 py-1.5 rounded-full text-xs border cursor-pointer transition-all',
                      role === r.value
                        ? 'bg-accent border-accent text-white font-semibold'
                        : 'bg-bg-card border-border-default text-text-secondary',
                    )}
                  >
                    {r.label}
                  </button>
                ))}
              </div>
            </div>

            {role === 'executor' && (
              <div className="flex flex-col gap-1.5">
                <Label>{t('employeeModal.specializations')}</Label>
                <div className="flex flex-wrap gap-1.5">
                  {SPEC_KEYS.map(key => (
                    <button
                      key={key}
                      onClick={() => toggleSpec(key)}
                      className={cn(
                        'px-2.5 py-1 rounded-full text-[11px] border cursor-pointer transition-all',
                        specs.includes(key)
                          ? 'bg-accent border-accent text-white font-semibold'
                          : 'bg-bg-card border-border-default text-text-secondary',
                      )}
                    >
                      {getSpecDisplay(key, t)}
                    </button>
                  ))}
                </div>
              </div>
            )}

            <div className="flex flex-col gap-1.5">
              <Label>{t('employeeModal.inviteHours')}</Label>
              <div className="flex gap-2">
                {EXPIRY_OPTIONS.map(o => (
                  <button
                    key={o.value}
                    onClick={() => setInvHours(o.value)}
                    className={cn(
                      'px-3 py-1.5 rounded-full text-xs border cursor-pointer transition-all',
                      invHours === o.value
                        ? 'bg-accent border-accent text-white font-semibold'
                        : 'bg-bg-card border-border-default text-text-secondary',
                    )}
                  >
                    {o.label}
                  </button>
                ))}
              </div>
            </div>

            <Button onClick={handleCreate} disabled={isPending} className="mt-1">
              {isPending ? t('common.creating') : t('employeeModal.inviteAction', 'Создать приглашение')}
            </Button>
          </div>
        )}

        {/* ===== Result after invite generation ===== */}
        {inviteResult && (
          <div className="flex flex-col gap-3">
            <div className="bg-emerald/10 border border-emerald/20 rounded-default p-3 text-sm text-emerald">
              {t('employeeModal.inviteCreated', 'Приглашение создано — отправьте ссылку кандидату. Сотрудник появится в «Ожидающих одобрения» после входа через бота.')}
            </div>

            <div className="flex flex-col gap-1.5">
              <Label>{t('employeeModal.inviteToken')}</Label>
              <div className="flex gap-2">
                <Input
                  readOnly
                  value={inviteResult.token}
                  className="font-mono text-xs flex-1"
                />
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => copyToClipboard(inviteResult.token)}
                >
                  {t('employeeModal.copyLink')}
                </Button>
              </div>
            </div>

            <div className="flex flex-col gap-1.5">
              <Label>{t('employeeModal.inviteLink')}</Label>
              <div className="flex gap-2">
                <Input
                  readOnly
                  value={inviteResult.bot_link}
                  className="text-xs flex-1"
                />
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => copyToClipboard(inviteResult.bot_link)}
                >
                  {t('employeeModal.copyLink')}
                </Button>
              </div>
            </div>

            <p className="text-xs text-text-muted">
              {t('employeeModal.inviteInstruction')}
            </p>

            <div className="flex gap-2 mt-1">
              <Button variant="outline" className="flex-1" onClick={() => reset()}>
                {t('employeeModal.addAnother')}
              </Button>
              <Button className="flex-1" onClick={handleClose}>
                {t('employeeModal.done')}
              </Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
