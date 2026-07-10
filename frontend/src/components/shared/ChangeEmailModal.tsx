import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
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
import { apiClient } from '@/api/client'
import { toast } from 'sonner'

interface Props {
  open: boolean
  onClose: () => void
}

// Лёгкая клиентская проверка формата (окончательную даёт бэкенд — EmailStr, 422).
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

export default function ChangeEmailModal({ open, onClose }: Props) {
  const { t } = useTranslation()
  const [email, setEmail] = useState('')
  const [initial, setInitial] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  // Юзер уже начал печатать — поздний ответ prefill не должен затирать ввод.
  const touched = useRef(false)

  // Подтягиваем текущий email при открытии, чтобы поле было предзаполнено.
  useEffect(() => {
    if (!open) return
    let cancelled = false
    touched.current = false
    setError('')
    apiClient
      .get('/api/v2/profile')
      .then((r) => {
        if (cancelled || touched.current) return
        const current = (r.data?.email as string | null) ?? ''
        setEmail(current)
        setInitial(current)
      })
      .catch(() => { /* пустое поле — не блокирующая ошибка */ })
    return () => { cancelled = true }
  }, [open])

  function handleClose() {
    setEmail('')
    setInitial('')
    setError('')
    setLoading(false)
    touched.current = false
    onClose()
  }

  async function submit() {
    const value = email.trim()
    if (!EMAIL_RE.test(value)) {
      setError(t('changeEmail.invalid'))
      return
    }
    setLoading(true)
    setError('')
    try {
      await apiClient.patch('/api/v2/profile', { email: value })
      toast.success(t('changeEmail.success'))
      handleClose()
    } catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
      // pydantic 422 отдаёт detail списком объектов — не показываем сырьё.
      setError(typeof detail === 'string' ? detail : t('changeEmail.invalid'))
    } finally {
      setLoading(false)
    }
  }

  const disabled = loading || !email.trim() || email.trim() === initial.trim()

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) handleClose() }}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{t('changeEmail.title')}</DialogTitle>
          <DialogDescription>{t('changeEmail.description')}</DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-3">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="ce-email">{t('changeEmail.email')}</Label>
            <Input
              id="ce-email"
              type="email"
              autoComplete="email"
              placeholder="name@example.com"
              value={email}
              onChange={(e) => { touched.current = true; setEmail(e.target.value) }}
              onKeyDown={(e) => { if (e.key === 'Enter' && !disabled) submit() }}
            />
          </div>

          {error && (
            <p className="text-xs text-red" role="alert">{error}</p>
          )}

          <Button onClick={submit} disabled={disabled} className="mt-1">
            {loading ? t('changeEmail.submitting') : t('changeEmail.submit')}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
