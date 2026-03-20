import { useState } from 'react'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useCreateEmployee, useCreateInvite } from '@/hooks/useEmployees'
import { SPEC_DISPLAY } from '@/utils/employeeUtils'
import { cn } from '@/lib/utils'
import { toast } from 'sonner'

interface Props {
  open: boolean
  onClose: () => void
}

const SPEC_KEYS = Object.keys(SPEC_DISPLAY)

const EXPIRY_OPTIONS = [
  { value: 1, label: '1 час' },
  { value: 24, label: '24 часа' },
  { value: 168, label: '7 дней' },
]

export default function AddEmployeeModal({ open, onClose }: Props) {
  // Form state
  const [firstName, setFirstName] = useState('')
  const [lastName, setLastName] = useState('')
  const [phone, setPhone] = useState('')
  const [role, setRole] = useState<'executor' | 'manager'>('executor')
  const [specs, setSpecs] = useState<string[]>([])
  const [empStatus, setEmpStatus] = useState<'approved' | 'pending'>('approved')
  const [invHours, setInvHours] = useState(24)

  // Result state — after creation
  const [inviteResult, setInviteResult] = useState<{
    token: string
    bot_link: string
    expires_at: string
  } | null>(null)

  const createEmployee = useCreateEmployee()
  const createInvite = useCreateInvite()

  function reset() {
    setFirstName('')
    setLastName('')
    setPhone('')
    setRole('executor')
    setSpecs([])
    setEmpStatus('approved')
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
    if (!firstName.trim() || !lastName.trim() || !phone.trim()) return

    const specsList = role === 'executor' ? specs : []

    // Step 1: create employee
    createEmployee.mutate(
      {
        first_name: firstName.trim(),
        last_name: lastName.trim(),
        phone: phone.trim(),
        role,
        specializations: specsList,
        status: empStatus,
      },
      {
        onSuccess: () => {
          // Step 2: generate invite link
          createInvite.mutate(
            {
              role,
              specializations: specsList,
              hours: invHours,
            },
            {
              onSuccess: (data) => {
                setInviteResult(data)
              },
              onError: () => {
                // Employee created but invite failed — still show success, just no link
                toast.info('Сотрудник создан, но не удалось сгенерировать приглашение')
              },
            },
          )
        },
      },
    )
  }

  async function copyToClipboard(text: string) {
    try {
      await navigator.clipboard.writeText(text)
      toast.success('Скопировано')
    } catch {
      toast.error('Не удалось скопировать')
    }
  }

  const isPending = createEmployee.isPending || createInvite.isPending
  const isCreateDisabled =
    !firstName.trim() || !lastName.trim() || !phone.trim() || isPending

  return (
    <Dialog open={open} onOpenChange={(v) => !v && handleClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Добавить сотрудника</DialogTitle>
          <DialogDescription>
            {inviteResult
              ? 'Сотрудник создан. Отправьте приглашение для подключения к боту.'
              : 'Заполните данные — сотрудник будет создан и получит ссылку-приглашение'}
          </DialogDescription>
        </DialogHeader>

        {/* ===== Form ===== */}
        {!inviteResult && (
          <div className="flex flex-col gap-3">
            <div className="grid grid-cols-2 gap-3">
              <div className="flex flex-col gap-1.5">
                <Label>Имя</Label>
                <Input value={firstName} onChange={e => setFirstName(e.target.value)} placeholder="Иван" />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label>Фамилия</Label>
                <Input value={lastName} onChange={e => setLastName(e.target.value)} placeholder="Петров" />
              </div>
            </div>

            <div className="flex flex-col gap-1.5">
              <Label>Телефон</Label>
              <Input value={phone} onChange={e => setPhone(e.target.value)} placeholder="+998901234567" />
            </div>

            <div className="flex flex-col gap-1.5">
              <Label>Роль</Label>
              <div className="flex gap-2">
                {([
                  { value: 'executor' as const, label: 'Исполнитель' },
                  { value: 'manager' as const, label: 'Менеджер' },
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
                <Label>Специализации</Label>
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
                      {SPEC_DISPLAY[key]}
                    </button>
                  ))}
                </div>
              </div>
            )}

            <div className="flex flex-col gap-1.5">
              <Label>Статус</Label>
              <div className="flex gap-2">
                {([
                  { value: 'approved' as const, label: 'Одобрен' },
                  { value: 'pending' as const, label: 'Ожидает одобрения' },
                ]).map(s => (
                  <button
                    key={s.value}
                    onClick={() => setEmpStatus(s.value)}
                    className={cn(
                      'px-3 py-1.5 rounded-full text-xs border cursor-pointer transition-all',
                      empStatus === s.value
                        ? 'bg-accent border-accent text-white font-semibold'
                        : 'bg-bg-card border-border-default text-text-secondary',
                    )}
                  >
                    {s.label}
                  </button>
                ))}
              </div>
            </div>

            <div className="flex flex-col gap-1.5">
              <Label>Срок действия приглашения</Label>
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

            <Button onClick={handleCreate} disabled={isCreateDisabled} className="mt-1">
              {isPending ? 'Создание...' : 'Создать и получить ссылку'}
            </Button>
          </div>
        )}

        {/* ===== Result after creation ===== */}
        {inviteResult && (
          <div className="flex flex-col gap-3">
            <div className="bg-emerald/10 border border-emerald/20 rounded-default p-3 text-sm text-emerald">
              Сотрудник {firstName} {lastName} успешно создан
            </div>

            <div className="flex flex-col gap-1.5">
              <Label>Токен приглашения</Label>
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
                  Копировать
                </Button>
              </div>
            </div>

            <div className="flex flex-col gap-1.5">
              <Label>Ссылка на бота</Label>
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
                  Копировать
                </Button>
              </div>
            </div>

            <p className="text-xs text-text-muted">
              Отправьте сотруднику ссылку на бота и токен. В боте нужно использовать команду{' '}
              <code className="bg-bg-surface px-1 py-0.5 rounded text-[11px]">/join {'<токен>'}</code>
            </p>

            <div className="flex gap-2 mt-1">
              <Button variant="outline" className="flex-1" onClick={() => reset()}>
                Добавить ещё
              </Button>
              <Button className="flex-1" onClick={handleClose}>
                Готово
              </Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
