import { useEffect, useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { useNavigate, useParams } from 'react-router'
import { useTranslation } from 'react-i18next'
import { DoorClosed, Home, PackageX, Pencil, RotateCcw, Send, UserX, Wrench, type LucideIcon } from 'lucide-react'
import { useTelegramSDK } from '../../hooks/useTelegramSDK'
import { apiErrorStatus } from '../../../utils/errorMessage'
import { MAX_REQUEST_TEXT_LENGTH } from '../../../constants'
import { reportProblem, type ProblemTemplate } from '../api'
import { useBackTo } from '../hooks/useSimpleNav'
import { ConfirmSheet, PRIMARY_BTN, ResultScreen, SECONDARY_BTN } from '../components/Ui'

// Кнопки-шаблоны; `other` — не кнопка, а «Отправить» под своим текстом.
const TEMPLATES: readonly { template: Exclude<ProblemTemplate, 'other'>; icon: LucideIcon }[] = [
  { template: 'no_material', icon: PackageX },
  { template: 'not_let_in', icon: DoorClosed },
  { template: 'resident_absent', icon: UserX },
  { template: 'need_master', icon: Wrench },
]

const SUCCESS_HOLD_MS = 1200

/** Сообщение об отказе без сырого текста бэкенда. */
function failureKey(err: unknown): string {
  const status = apiErrorStatus(err)
  if (status === 409) return 'twa.simple.final.closed'
  if (status === 403 || status === 404) return 'twa.simple.final.notYours'
  return 'twa.simple.problem.failed'
}

/** «Проблема»: шаблон-кнопка (+ необязательный текст) → «Да / Нет» → менеджеру. */
export default function ProblemPage() {
  const { number = '' } = useParams()
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { notify } = useTelegramSDK()
  const taskPath = `/twa/s/task/${encodeURIComponent(number)}`
  useBackTo(taskPath)

  const [writing, setWriting] = useState(false)
  const [text, setText] = useState('')
  const [chosen, setChosen] = useState<ProblemTemplate | null>(null)

  const send = useMutation({
    mutationFn: (template: ProblemTemplate) => reportProblem(number, template, text),
    onSuccess: () => notify('success'),
    onError: () => notify('error'),
  })

  useEffect(() => {
    if (!send.isSuccess) return
    const id = window.setTimeout(() => navigate(taskPath, { replace: true }), SUCCESS_HOLD_MS)
    return () => window.clearTimeout(id)
  }, [send.isSuccess, navigate, taskPath])

  if (send.isSuccess) return <ResultScreen ok title={t('twa.simple.problem.sent')} />

  if (send.isError && chosen) {
    const retryable = failureKey(send.error) === 'twa.simple.problem.failed'
    return (
      <ResultScreen ok={false} title={t(failureKey(send.error))}>
        {retryable && (
          <button type="button" onClick={() => send.mutate(chosen)} className={`${PRIMARY_BTN} bg-white text-red-700`}>
            <RotateCcw size={30} aria-hidden /> {t('twa.simple.error.retry')}
          </button>
        )}
        {!retryable && (
          <button type="button" onClick={() => navigate('/twa/s', { replace: true })} className={`${PRIMARY_BTN} bg-white text-red-700`}>
            <Home size={30} aria-hidden /> {t('twa.simple.done.toMine')}
          </button>
        )}
      </ResultScreen>
    )
  }

  return (
    <main className="p-3 pb-[calc(12px+env(safe-area-inset-bottom))] flex flex-col gap-3">
      {TEMPLATES.map(({ template, icon: Icon }) => (
        <button
          key={template}
          type="button"
          onClick={() => setChosen(template)}
          className="w-full min-h-[64px] rounded-2xl bg-white dark:bg-gray-800 border-2 border-gray-300 dark:border-gray-600 px-4 flex items-center gap-4 text-[22px] font-bold text-left active:scale-[0.98] transition-transform"
        >
          <Icon size={32} className="shrink-0 text-amber-600 dark:text-amber-400" aria-hidden />
          {t(`twa.simple.problem.templates.${template}`)}
        </button>
      ))}

      {writing ? (
        <textarea
          autoFocus
          value={text}
          maxLength={MAX_REQUEST_TEXT_LENGTH}
          onChange={(e) => setText(e.target.value)}
          placeholder={t('twa.simple.problem.placeholder')}
          className="w-full min-h-[120px] rounded-2xl border-2 border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 p-3 text-[18px] focus:outline-none focus:ring-2 focus:ring-emerald-500"
        />
      ) : (
        <button
          type="button"
          onClick={() => setWriting(true)}
          className={`${SECONDARY_BTN} border-2 border-dashed border-gray-400 text-gray-700 dark:text-gray-200`}
        >
          <Pencil size={26} aria-hidden /> {t('twa.simple.problem.write')}
        </button>
      )}

      {/* Проблема своими словами (решение владельца: «проблема = комментарий
          текстом») — шаблон `other`, без выбора кнопки-шаблона. */}
      {text.trim() && (
        <button type="button" onClick={() => setChosen('other')} className={`${PRIMARY_BTN} bg-emerald-600 text-white`}>
          <Send size={30} aria-hidden /> {t('twa.simple.done.send')}
        </button>
      )}

      {chosen && (
        <ConfirmSheet
          title={t('twa.simple.problem.confirm')}
          busy={send.isPending}
          onNo={() => setChosen(null)}
          onYes={() => send.mutate(chosen)}
        >
          {chosen !== 'other' && (
            <p className="text-[20px] text-center font-semibold">{t(`twa.simple.problem.templates.${chosen}`)}</p>
          )}
          {text.trim() && (
            <p className="text-[18px] text-center break-words whitespace-pre-line text-gray-700 dark:text-gray-300">{text.trim()}</p>
          )}
        </ConfirmSheet>
      )}
    </main>
  )
}
