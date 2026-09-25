import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate, useSearchParams } from 'react-router'
import { useTranslation } from 'react-i18next'
import { twaClient } from '../../twaClient'
import { useTelegramSDK } from '../../hooks/useTelegramSDK'
import { notifyError } from '../../utils/errors'
import { markLangChosen } from '../langFlag'

type Lang = 'uz' | 'uz_cyrl' | 'ru'

// Самоназвания языков — не переводятся; других подписей на экране нет.
const LANGS: readonly { code: Lang; label: string }[] = [
  { code: 'uz', label: 'O‘zbekcha' },
  { code: 'uz_cyrl', label: 'Ўзбекча' },
  { code: 'ru', label: 'Русский' },
]

/** Только внутренние пути простого режима — `next` приходит из URL. */
function safeNext(next: string | null): string {
  return next && /^\/twa\/s(\/|$|\?)/.test(next) && !next.startsWith('/twa/s/lang') ? next : '/twa/s'
}

/** Выбор языка: три кнопки по 88 px. Первый вход в простой режим. */
export default function LangPage() {
  const { i18n } = useTranslation()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const queryClient = useQueryClient()
  const { notify } = useTelegramSDK()

  const save = useMutation({
    mutationFn: (language: Lang) => twaClient.patch('/api/v2/profile', { language }),
    onSuccess: (_, language) => {
      notify('success')
      markLangChosen()
      void i18n.changeLanguage(language)
      queryClient.invalidateQueries({ queryKey: ['twa', 'profile'] })
      navigate(safeNext(params.get('next')), { replace: true })
    },
    onError: (err: unknown) => {
      notify('error')
      notifyError(err)
    },
  })

  return (
    <div className="min-h-screen bg-gray-100 dark:bg-gray-950 flex flex-col justify-center gap-4 p-4">
      {LANGS.map(({ code, label }) => (
        <button
          key={code}
          type="button"
          lang={code === 'uz_cyrl' ? 'uz-Cyrl' : code}
          disabled={save.isPending}
          onClick={() => save.mutate(code)}
          className="w-full h-[88px] rounded-2xl bg-white dark:bg-gray-800 border-2 border-gray-300 dark:border-gray-600 text-[28px] font-bold text-gray-900 dark:text-gray-50 disabled:opacity-60 active:scale-[0.98] transition-transform"
        >
          {label}
        </button>
      ))}
    </div>
  )
}
