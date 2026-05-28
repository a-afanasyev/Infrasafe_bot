import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Send } from 'lucide-react'
import { twaClient } from '../twaClient'
import { useTelegramSDK } from '../hooks/useTelegramSDK'
import { notifyError } from '../utils/errors'

interface Comment {
  id: number
  user_id: number
  comment_text: string
  created_at?: string | null
}

interface Profile {
  id: number
}

interface Props {
  requestNumber: string
}

/**
 * Two-way clarification dialog backed by request comments. Both the applicant
 * (owner) and the assigned executor can read and post — the executor's
 * "Уточнение" question lands here as the first message, the applicant answers,
 * and the executor resumes work. Own messages align right (emerald).
 */
export default function CommentThread({ requestNumber }: Props) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const { haptic } = useTelegramSDK()
  const [text, setText] = useState('')

  const { data: comments = [] } = useQuery<Comment[]>({
    queryKey: ['comments', requestNumber],
    queryFn: () => twaClient.get(`/api/v2/requests/${requestNumber}/comments`).then((r) => r.data),
    enabled: !!requestNumber,
    // Poll so the other party's reply shows up without a manual refresh —
    // only while the detail page (and thus this thread) is mounted.
    refetchInterval: 10_000,
  })

  const { data: profile } = useQuery<Profile>({
    queryKey: ['profile'],
    queryFn: () => twaClient.get('/api/v2/profile').then((r) => r.data),
    staleTime: 60_000,
  })

  const post = useMutation({
    mutationFn: (body: string) =>
      twaClient.post(`/api/v2/requests/${requestNumber}/comments`, { text: body }),
    onSuccess: () => {
      haptic('selection')
      setText('')
      queryClient.invalidateQueries({ queryKey: ['comments', requestNumber] })
    },
    onError: (err: unknown) => notifyError(err),
  })

  const send = () => {
    const body = text.trim()
    if (body) post.mutate(body)
  }

  return (
    <div className="bg-white dark:bg-gray-800 rounded-2xl p-4 border border-gray-100 dark:border-gray-700 mb-3">
      <h3 className="font-semibold text-[13px] text-gray-900 dark:text-gray-100 mb-3">{t('twa.detail.dialog')}</h3>

      {comments.length === 0 ? (
        <p className="text-[12px] text-gray-400 mb-3">{t('twa.detail.dialogEmpty')}</p>
      ) : (
        <div className="space-y-2 mb-3">
          {comments.map((c) => {
            const mine = profile?.id === c.user_id
            return (
              <div key={c.id} className={`flex ${mine ? 'justify-end' : 'justify-start'}`}>
                <div
                  className={`max-w-[80%] rounded-2xl px-3 py-2 text-[12px] whitespace-pre-line ${
                    mine
                      ? 'bg-emerald-500 text-white'
                      : 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-200'
                  }`}
                >
                  {c.comment_text}
                  {c.created_at && (
                    <span className={`block text-[10px] mt-1 ${mine ? 'text-emerald-100' : 'text-gray-400'}`}>
                      {new Date(c.created_at).toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })}
                    </span>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}

      <div className="flex items-end gap-2">
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={t('twa.detail.dialogPlaceholder')}
          rows={1}
          className="flex-1 bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-xl px-3 py-2 text-[13px] resize-none focus:outline-none focus:ring-2 focus:ring-emerald-500"
        />
        <button
          onClick={send}
          disabled={!text.trim() || post.isPending}
          className="shrink-0 w-10 h-10 rounded-xl bg-emerald-500 text-white flex items-center justify-center disabled:opacity-50"
        >
          <Send size={16} />
        </button>
      </div>
    </div>
  )
}
