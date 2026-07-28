import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { ResidentProfile } from '../../types/api'
import {
  useApproveVerification,
  useRejectVerification,
  useRequestDocuments,
} from '../../hooks/useResidents'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import ConfirmDialog from '../shared/ConfirmDialog'

interface Props {
  resident: ResidentProfile
}

const DOCUMENT_TYPES = [
  'passport', 'property_deed', 'rental_agreement', 'utility_bill', 'other',
] as const

export default function ResidentVerificationActions({ resident }: Props) {
  const { t } = useTranslation()
  const [requestOpen, setRequestOpen] = useState(false)
  const [types, setTypes] = useState<string[]>([])
  const [comment, setComment] = useState('')
  const [approveOpen, setApproveOpen] = useState(false)
  const [rejectOpen, setRejectOpen] = useState(false)
  const [notes, setNotes] = useState('')

  const request = useRequestDocuments(resident.id)
  const approve = useApproveVerification(resident.id)
  const reject = useRejectVerification(resident.id)

  const busy = request.isPending || approve.isPending || reject.isPending
  // Решение принимается только по открытой оси верификации — бэкенд отвечает
  // 409 на уже закрытую, и показывать кнопку, которая упадёт, незачем.
  const decidable = resident.verification_status === 'pending'
    || resident.verification_status === 'requested'

  const toggle = (type: string) =>
    setTypes(prev => prev.includes(type) ? prev.filter(x => x !== type) : [...prev, type])

  return (
    <div className="flex flex-col gap-3">
      <div className="flex gap-2 flex-wrap">
        <Button variant="outline" size="sm" disabled={busy}
                onClick={() => { setTypes([]); setComment(''); setRequestOpen(true) }}>
          {t('residents.requestDocuments')}
        </Button>
        {decidable && (
          <>
            <Button size="sm" disabled={busy} onClick={() => setApproveOpen(true)}>
              {t('residents.verifyResident')}
            </Button>
            <Button variant="destructive" size="sm" disabled={busy}
                    onClick={() => { setNotes(''); setRejectOpen(true) }}>
              {t('residents.rejectVerification')}
            </Button>
          </>
        )}
      </div>

      {/* Запрос документов */}
      {requestOpen && (
        <Dialog open onOpenChange={o => { if (!o) setRequestOpen(false) }}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>{t('residents.requestDocumentsTitle')}</DialogTitle>
            </DialogHeader>
            <div className="flex flex-col gap-3">
              <div className="flex flex-col gap-1.5">
                {DOCUMENT_TYPES.map(type => (
                  <label key={type}
                         className="flex items-center gap-2 text-[13px] text-text-secondary cursor-pointer">
                    <input type="checkbox" checked={types.includes(type)}
                           onChange={() => toggle(type)} />
                    {t(`residents.documentType.${type}`)}
                  </label>
                ))}
              </div>
              <Textarea
                value={comment}
                onChange={e => setComment(e.target.value)}
                placeholder={t('residents.requestComment')}
                aria-label={t('residents.requestComment')}
              />
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setRequestOpen(false)}>
                {t('common.cancel')}
              </Button>
              <Button
                disabled={types.length === 0 || comment.trim().length < 3 || busy}
                onClick={() => request.mutate(
                  { document_types: types, comment: comment.trim() },
                  { onSuccess: () => setRequestOpen(false) },
                )}
              >
                {t('residents.requestSubmit')}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}

      {/* Подтверждение личности — с честным текстом о последствиях */}
      <ConfirmDialog
        open={approveOpen}
        onOpenChange={setApproveOpen}
        title={t('residents.verifyConfirm')}
        description={t('residents.verifyConfirmDesc')}
        confirmLabel={t('residents.verifyResident')}
        variant="warning"
        loading={approve.isPending}
        onConfirm={() => approve.mutate({})}
      />

      {/* Отказ */}
      {rejectOpen && (
        <Dialog open onOpenChange={o => { if (!o) setRejectOpen(false) }}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>{t('residents.rejectVerificationTitle')}</DialogTitle>
            </DialogHeader>
            <Textarea
              value={notes}
              onChange={e => setNotes(e.target.value)}
              placeholder={t('residents.rejectVerificationReason')}
              aria-label={t('residents.rejectVerificationReason')}
              autoFocus
            />
            <DialogFooter>
              <Button variant="outline" onClick={() => setRejectOpen(false)}>
                {t('common.cancel')}
              </Button>
              <Button
                variant="destructive"
                disabled={notes.trim().length < 3 || busy}
                onClick={() => reject.mutate(
                  { notes: notes.trim() },
                  { onSuccess: () => setRejectOpen(false) },
                )}
              >
                {t('residents.rejectVerification')}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}
    </div>
  )
}
