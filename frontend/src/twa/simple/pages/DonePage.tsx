import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router'
import { useTranslation } from 'react-i18next'
import { Camera, Home, Play, RotateCcw, Send } from 'lucide-react'
import { useTaskCard } from '../api'
import { canComplete } from '../model'
import { useTelegramSDK } from '../../hooks/useTelegramSDK'
import { downscaleImage } from '../../utils/downscaleImage'
import { notifyError } from '../../utils/errors'
import { useBackTo } from '../hooks/useSimpleNav'
import { blobToDataUrl } from '../hooks/useResidentPhoto'
import { PRIMARY_BTN, ResultScreen, SECONDARY_BTN, WaitManagerPlate } from '../components/Ui'
import { FINAL_REASON_KEY, useCompletionQueue } from '../queue/CompletionQueue'
import type { FinalReason, SendOutcome } from '../queue/types'

// Фото «после» — до 1280 px по большей стороне: хватает, чтобы увидеть
// работу, и уходит по плохой сети за разумное время.
const DOWNSCALE = { maxDimension: 1280, thresholdBytes: 400_000 }
const SUCCESS_HOLD_MS = 1500

type Stage =
  | { kind: 'camera' }
  | { kind: 'preview'; file: File; url: string }
  | { kind: 'sending'; url?: string }
  | { kind: 'sent' }
  | { kind: 'queued'; id: string; noShift: boolean }
  | { kind: 'final'; reason: FinalReason }

/** «Готово»: сразу камера → превью «Заново / Отправить» → галка или крест. */
export default function DonePage() {
  const { number = '' } = useParams()
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { notify } = useTelegramSDK()
  const queue = useCompletionQueue()
  const inputRef = useRef<HTMLInputElement>(null)
  const [stage, setStage] = useState<Stage>({ kind: 'camera' })
  const taskPath = `/twa/s/task/${encodeURIComponent(number)}`
  useBackTo(taskPath)

  const openCamera = () => inputRef.current?.click()

  // «Готово» — только из «В работе» (канон EXECUTOR_COMPLETE). Статус берём
  // из карточки; без сети и без кэша камеру не блокируем — для того и очередь.
  const { data: task, isError, fetchStatus } = useTaskCard(number)
  const blocked = !!task && !canComplete(task.status)
  const settled = !!task || isError || fetchStatus === 'paused'

  // Камера — сразу: переход сюда был по тапу «Готово», жест ещё действует.
  // Если WebView не дал открыть без жеста — на экране большая кнопка «Камера».
  const autoOpened = useRef(false)
  useEffect(() => {
    if (autoOpened.current || blocked || !settled) return
    autoOpened.current = true
    inputRef.current?.click()
  }, [blocked, settled])

  useEffect(() => {
    if (stage.kind !== 'sent') return
    const id = window.setTimeout(() => navigate('/twa/s', { replace: true }), SUCCESS_HOLD_MS)
    return () => window.clearTimeout(id)
  }, [stage.kind, navigate])

  const onPicked = async (file: File | undefined) => {
    if (!file) return
    try {
      setStage({ kind: 'preview', file, url: await blobToDataUrl(file) })
    } catch {
      setStage({ kind: 'camera' })
    }
  }

  const show = (id: string, outcome: SendOutcome) => {
    if (outcome.kind === 'sent') {
      notify('success')
      setStage({ kind: 'sent' })
    } else if (outcome.kind === 'queued') {
      notify('error')
      setStage({ kind: 'queued', id, noShift: outcome.noShift })
    } else {
      notify('error')
      setStage({ kind: 'final', reason: outcome.reason })
    }
  }

  const send = async (file: File, url: string) => {
    setStage({ kind: 'sending', url })
    try {
      const photo = await downscaleImage(file, DOWNSCALE)
      const { id, outcome } = await queue.submit(number, photo, photo.name || `${number}.jpg`)
      show(id, outcome)
    } catch (err) {
      // Сбой самого хранилища (не сети): фото на экране, можно нажать ещё раз.
      notify('error')
      notifyError(err)
      setStage({ kind: 'preview', file, url })
    }
  }

  const retry = async (id: string) => {
    setStage({ kind: 'sending' })
    show(id, await queue.retry(id))
  }

  const input = (
    <input
      ref={inputRef}
      type="file"
      accept="image/*"
      capture="environment"
      className="hidden"
      data-testid="camera-input"
      onChange={(e) => {
        void onPicked(e.target.files?.[0])
        e.target.value = ''
      }}
    />
  )

  if (stage.kind === 'sent') return <ResultScreen ok title={t('twa.simple.done.sent')} />

  if (stage.kind === 'queued') {
    return (
      <ResultScreen
        ok={false}
        title={t('twa.simple.done.failed')}
        subtitle={stage.noShift ? t('twa.simple.done.noShift') : t('twa.simple.done.savedLater')}
      >
        {stage.noShift ? (
          <button type="button" onClick={() => navigate('/twa/s/shift')} className={`${PRIMARY_BTN} bg-white text-red-700`}>
            <Play size={30} aria-hidden /> {t('twa.simple.pool.startShift')}
          </button>
        ) : (
          <button type="button" onClick={() => void retry(stage.id)} className={`${PRIMARY_BTN} bg-white text-red-700`}>
            <RotateCcw size={30} aria-hidden /> {t('twa.simple.done.retry')}
          </button>
        )}
      </ResultScreen>
    )
  }

  if (stage.kind === 'final') {
    const retake = stage.reason === 'bad_photo'
    return (
      <ResultScreen ok={false} title={t('twa.simple.done.failed')} subtitle={t(FINAL_REASON_KEY[stage.reason])}>
        {input}
        {retake ? (
          <button type="button" onClick={openCamera} className={`${PRIMARY_BTN} bg-white text-red-700`}>
            <Camera size={30} aria-hidden /> {t('twa.simple.done.retake')}
          </button>
        ) : (
          <button type="button" onClick={() => navigate('/twa/s', { replace: true })} className={`${PRIMARY_BTN} bg-white text-red-700`}>
            <Home size={30} aria-hidden /> {t('twa.simple.done.toMine')}
          </button>
        )}
      </ResultScreen>
    )
  }

  // Заявка не «В работе» (например, «Возвращена» — решает менеджер): не камера, а плашка.
  if (stage.kind === 'camera' && blocked) {
    return (
      <main className="min-h-[80vh] p-3 flex flex-col justify-center gap-4">
        <WaitManagerPlate />
        <button
          type="button"
          onClick={() => navigate('/twa/s', { replace: true })}
          className={`${SECONDARY_BTN} border-2 border-gray-400 bg-white dark:bg-gray-900 text-gray-800 dark:text-gray-100`}
        >
          <Home size={26} aria-hidden /> {t('twa.simple.done.toMine')}
        </button>
      </main>
    )
  }

  return (
    <main className="min-h-screen p-3 pb-[calc(12px+env(safe-area-inset-bottom))] flex flex-col gap-4">
      {input}
      {stage.kind === 'camera' && (
        <div className="flex-1 flex flex-col items-center justify-center gap-6 py-10 text-center">
          <Camera size={96} className="text-gray-500" aria-hidden />
          <p className="text-[24px] font-bold">{t('twa.simple.done.shoot')}</p>
          <button type="button" onClick={openCamera} className={`${PRIMARY_BTN} bg-emerald-600 text-white`}>
            <Camera size={32} aria-hidden /> {t('twa.simple.done.camera')}
          </button>
        </div>
      )}
      {(stage.kind === 'preview' || stage.kind === 'sending') && (
        <>
          {stage.url && (
            <img src={stage.url} alt="" className="w-full max-h-[60vh] object-contain rounded-2xl bg-black" />
          )}
          <div className="mt-auto flex flex-col gap-3">
            <button
              type="button"
              disabled={stage.kind === 'sending'}
              onClick={() => stage.kind === 'preview' && void send(stage.file, stage.url)}
              className={`${PRIMARY_BTN} bg-emerald-600 text-white`}
            >
              <Send size={30} aria-hidden />
              {stage.kind === 'sending' ? t('twa.simple.done.sending') : t('twa.simple.done.send')}
            </button>
            <button
              type="button"
              disabled={stage.kind === 'sending'}
              onClick={openCamera}
              className={`${SECONDARY_BTN} border-2 border-gray-400 bg-white dark:bg-gray-900 text-gray-800 dark:text-gray-100`}
            >
              <RotateCcw size={26} aria-hidden /> {t('twa.simple.done.retake')}
            </button>
          </div>
        </>
      )}
    </main>
  )
}
