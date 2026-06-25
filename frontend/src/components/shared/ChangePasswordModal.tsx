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
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { apiClient } from '@/api/client'
import { useAuthStore } from '@/stores/authStore'
import { toast } from 'sonner'

interface Props {
  open: boolean
  onClose: () => void
}

const MIN_LENGTH = 8

export default function ChangePasswordModal({ open, onClose }: Props) {
  const { t } = useTranslation()
  // AUD3-16: if the user already has a password this is a CHANGE and the
  // backend requires the current password as proof-of-presence. has_password
  // comes from /profile (authStore); a stale/undefined flag is covered by the
  // server-driven reveal in the catch block below.
  const hasPassword = useAuthStore((s) => s.user?.has_password)
  const [current, setCurrent] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  // Whether to show the "current password" field: driven by has_password, but
  // can be force-revealed if the server rejects a change without it.
  const [showCurrent, setShowCurrent] = useState(false)

  const currentNeeded = hasPassword === true || showCurrent

  function reset() {
    setCurrent('')
    setPassword('')
    setConfirm('')
    setError('')
    setLoading(false)
    setShowCurrent(false)
  }

  function handleClose() {
    reset()
    onClose()
  }

  async function submit() {
    if (currentNeeded && !current) {
      setError(t('changePassword.currentRequired'))
      return
    }
    if (password.length < MIN_LENGTH) {
      setError(t('changePassword.tooShort'))
      return
    }
    if (password !== confirm) {
      setError(t('changePassword.mismatch'))
      return
    }
    setLoading(true)
    setError('')
    try {
      await apiClient.post('/api/v2/auth/set-password', {
        password,
        confirm_password: confirm,
        ...(currentNeeded ? { current_password: current } : {}),
      })
      toast.success(t('changePassword.success'))
      handleClose()
    } catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      if (detail === 'current_password_required') {
        // Safety net: has_password flag was stale — reveal the field.
        setShowCurrent(true)
        setError(t('changePassword.currentRequired'))
      } else if (detail === 'current_password_invalid') {
        setError(t('changePassword.currentInvalid'))
      } else {
        setError(detail ?? t('changePassword.genericError'))
      }
    } finally {
      setLoading(false)
    }
  }

  const disabled = loading || !password || !confirm || (currentNeeded && !current)

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) handleClose() }}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{t('changePassword.title')}</DialogTitle>
          <DialogDescription>{t('changePassword.description')}</DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-3">
          {currentNeeded && (
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="cp-current">{t('changePassword.currentPassword')}</Label>
              <Input
                id="cp-current"
                type="password"
                autoComplete="current-password"
                value={current}
                onChange={(e) => setCurrent(e.target.value)}
              />
            </div>
          )}

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="cp-new">{t('changePassword.newPassword')}</Label>
            <Input
              id="cp-new"
              type="password"
              autoComplete="new-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="cp-confirm">{t('changePassword.confirmPassword')}</Label>
            <Input
              id="cp-confirm"
              type="password"
              autoComplete="new-password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter' && !disabled) submit() }}
            />
          </div>

          {error && (
            <p className="text-xs text-red" role="alert">{error}</p>
          )}

          <Button onClick={submit} disabled={disabled} className="mt-1">
            {loading ? t('changePassword.submitting') : t('changePassword.submit')}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
