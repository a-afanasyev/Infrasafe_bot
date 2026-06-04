import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { apiClient } from '../../api/client'
import {
  useFeedbackDetail,
  useUpdateFeedback,
  type FeedbackStatus,
} from '../../hooks/useFeedback'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { ImageOff } from 'lucide-react'

const ALL_STATUSES: FeedbackStatus[] = ['new', 'in_review', 'resolved']
// Совпадает с backend _TRANSITIONS.
const TRANSITIONS: Record<FeedbackStatus, FeedbackStatus[]> = {
  new: ['in_review', 'resolved'],
  in_review: ['resolved', 'new'],
  resolved: ['in_review'],
}

interface Props {
  feedbackId: number
  onClose: () => void
}

export default function FeedbackDetailModal({ feedbackId, onClose }: Props) {
  const { t } = useTranslation()
  const { data: fb, isLoading } = useFeedbackDetail(feedbackId)
  const update = useUpdateFeedback(feedbackId)
  const [reply, setReply] = useState('')

  return (
    <Dialog open onOpenChange={(open) => { if (!open) onClose() }}>
      <DialogContent className="max-w-[560px] max-h-[88vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>
            {fb ? t(`feedback.${fb.type}`) : t('feedback.title')}
          </DialogTitle>
        </DialogHeader>

        {isLoading || !fb ? (
          <div className="text-sm text-text-secondary py-6 text-center">{t('common.loading')}</div>
        ) : (
          <div className="flex flex-col gap-4">
            <div className="flex flex-wrap gap-x-4 gap-y-1 text-[13px] text-text-secondary">
              <span>{t('feedback.author')}: <b className="text-text-primary">{fb.author_name || '—'}</b></span>
              {fb.author_phone && <span>{fb.author_phone}</span>}
              <span>{fb.source === 'twa' ? t('feedback.sourceTwa') : t('feedback.sourceBot')}</span>
            </div>

            <div className="rounded-lg bg-bg-surface p-3 text-[14px] whitespace-pre-wrap text-text-primary">
              {fb.text}
            </div>

            {fb.media_ids.length > 0 && (
              <div className="flex flex-wrap gap-2">
                {fb.media_ids.map((mid) => (
                  <FeedbackPhoto key={mid} feedbackId={feedbackId} mediaId={mid} />
                ))}
              </div>
            )}

            {/* Статус */}
            <div>
              <p className="text-[13px] font-medium mb-1.5">{t('feedback.changeStatus')}</p>
              <div className="flex gap-2">
                {ALL_STATUSES.map((s) => {
                  const isCurrent = s === fb.status
                  const allowed = isCurrent || TRANSITIONS[fb.status]?.includes(s)
                  return (
                    <Button
                      key={s}
                      size="sm"
                      variant={isCurrent ? 'default' : 'outline'}
                      disabled={!allowed || isCurrent || update.isPending}
                      onClick={() => update.mutate({ status: s })}
                    >
                      {t(`feedback.${s}`)}
                    </Button>
                  )
                })}
              </div>
            </div>

            {/* Ответ */}
            <div>
              <p className="text-[13px] font-medium mb-1.5">{t('feedback.reply')}</p>
              {fb.reply && (
                <div className="rounded-lg border border-border-default p-3 text-[13px] mb-2 whitespace-pre-wrap">
                  {fb.reply}
                </div>
              )}
              <Textarea
                value={reply}
                onChange={(e) => setReply(e.target.value)}
                placeholder={t('feedback.replyPlaceholder')}
                rows={3}
              />
              <Button
                className="mt-2"
                size="sm"
                disabled={!reply.trim() || update.isPending}
                onClick={() => update.mutate({ reply: reply.trim() }, { onSuccess: () => setReply('') })}
              >
                {t('feedback.send')}
              </Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}

// Site-wide CSP запрещает blob: в img-src → грузим байты с Bearer и конвертируем
// в data: URL (как twa/MediaGallery). data: URL не требует revoke — собирается GC
// вместе со state при размонтировании.
function FeedbackPhoto({ feedbackId, mediaId }: { feedbackId: number; mediaId: number }) {
  const [url, setUrl] = useState<string | null>(null)
  const [errored, setErrored] = useState(false)

  useEffect(() => {
    let cancelled = false
    apiClient
      .get(`/api/v2/feedback/${feedbackId}/media/${mediaId}/file`, { responseType: 'blob' })
      .then((r) => new Promise<string>((resolve, reject) => {
        const reader = new FileReader()
        reader.onload = () => typeof reader.result === 'string' ? resolve(reader.result) : reject(new Error('bad'))
        reader.onerror = () => reject(reader.error)
        reader.readAsDataURL(r.data as Blob)
      }))
      .then((dataUrl) => { if (!cancelled) setUrl(dataUrl) })
      .catch(() => { if (!cancelled) setErrored(true) })
    return () => { cancelled = true }
  }, [feedbackId, mediaId])

  if (errored) {
    return (
      <div className="w-24 h-24 rounded-lg border border-border-default bg-bg-surface flex items-center justify-center text-text-secondary">
        <ImageOff size={20} />
      </div>
    )
  }
  return (
    <div className="w-24 h-24 rounded-lg overflow-hidden border border-border-default bg-bg-surface">
      {url && <img src={url} alt="" className="w-full h-full object-cover" />}
    </div>
  )
}
