import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router'
import { useTranslation } from 'react-i18next'
import { Camera, Home, Play, RotateCcw, Send } from 'lucide-react'
import { useTaskCard } from '../api'
import { canComplete, isClosed } from '../model'
import { useTelegramSDK } from '../../hooks/useTelegramSDK'
import { downscaleImage } from '../../utils/downscaleImage'
import { notifyError } from '../../utils/errors'
import { useBackTo } from '../hooks/useSimpleNav'
import { blobToDataUrl } from '../hooks/useResidentPhoto'
import { ClosedPlate, Loading, PRIMARY_BTN, ResultScreen, SECONDARY_BTN, WaitManagerPlate } from '../components/Ui'
import { FINAL_REASON_KEY, useCompletionQueue } from '../queue/CompletionQueue'
import type { FinalReason, SendOutcome } from '../queue/types'

// Фото «после» — до 1280 px по большей стороне: хватает, чтобы увидеть
// работу, и уходит по плохой сети за разумное время.
const DOWNSCALE = { maxDimension: 1280, thresholdBytes: 400_000 }
/** = COMPLETION_PHOTO_MAX_BYTES бэкенда: больше — 413, слать бессмысленно. */
const MAX_PHOTO_BYTES = 8 * 1024 * 1024
const SUCCESS_HOLD_MS = 1500
/** Свежая карточка не пришла (плохая сеть, запрос висит) — решаем по кэшу, не держим скелетон. */
const CARD_WAIT_MS = 4000

type Stage =
  | { kind: 'camera' }
  | { kind: 'processing' }
  | { kind: 'tooBig' }
  | { kind: 'preview'; photo: File; url: string }
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
  const toMine = () => navigate('/twa/s', { replace: true })

  // «Готово» — только из «В работе» (канон EXECUTOR_COMPLETE). Решаем по
  // СВЕЖЕЙ карточке (кэш мог устареть: заявку отменили); без сети — камеру
  // не блокируем, для того и очередь. fresh: карточку только что открыли —
  // кэш моложе staleTime, без принудительного запроса isFetchedAfterMount
  // навсегда false и экран висит на скелетоне.
  const { data: task, isError, isFetchedAfterMount, fetchStatus } = useTaskCard(number, { fresh: true })
  const [waitedLong, setWaitedLong] = useState(false)
  useEffect(() => {
    const id = window.setTimeout(() => setWaitedLong(true), CARD_WAIT_MS)
    return () => window.clearTimeout(id)
  }, [])
  const settled = isFetchedAfterMount || isError || fetchStatus === 'paused' || waitedLong
  const closed = settled && !!task && isClosed(task.status)
  const blocked = settled && !!task && !canComplete(task.status)

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

  // Сжимаем сразу после съёмки: превью строится из уменьшенной копии (одна
  // копия в памяти), и отправляется ровно то, что исполнитель видел.
  const onPicked = async (file: File | undefined) => {
    if (!file) return
    setStage({ kind: 'processing' })
    try {
      const photo = await downscaleImage(file, DOWNSCALE)
      if (photo.size > MAX_PHOTO_BYTES) {
        notify('error')
        setStage({ kind: 'tooBig' })
        return
      }
      setStage({ kind: 'preview', photo, url: await blobToDataUrl(photo) })
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

  const send = async (photo: File, url: string) => {
    setStage({ kind: 'sending', url })
    try {
      const { id, outcome } = await queue.submit({
        requestNumber: number,
        photo,
        fileName: photo.name || `${number}.jpg`,
        label: task?.address ?? undefined,
      })
      show(id, outcome)
    } catch (err) {
      // Сбой самого хранилища (не сети): фото на экране, можно нажать ещё раз.
      notify('error')
      notifyError(err)
      setStage({ kind: 'preview', photo, url })
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

  const toMineButton = (
    <button type="button" onClick={toMine} className={`${SECONDARY_BTN} border-2 border-white text-white`}>
      <Home size={26} aria-hidden /> {t('twa.simple.done.toMine')}
    </button>
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
        {toMineButton}
      </ResultScreen>
    )
  }

  if (stage.kind === 'final' || stage.kind === 'tooBig') {
    const retake = stage.kind === 'tooBig' || stage.reason === 'bad_photo'
    const subtitle = stage.kind === 'tooBig' ? t('twa.simple.done.tooBig') : t(FINAL_REASON_KEY[stage.reason])
    return (
      <ResultScreen ok={false} title={t('twa.simple.done.failed')} subtitle={subtitle}>
        {input}
        {retake ? (
          <button type="button" onClick={openCamera} className={`${PRIMARY_BTN} bg-white text-red-700`}>
            <Camera size={30} aria-hidden /> {t('twa.simple.done.retake')}
          </button>
        ) : (
          <button type="button" onClick={toMine} className={`${PRIMARY_BTN} bg-white text-red-700`}>
            <Home size={30} aria-hidden /> {t('twa.simple.done.toMine')}
          </button>
        )}
      </ResultScreen>
    )
  }

  // Закрытую заявку не закрыть; не «В работе» (например, «Возвращена») —
  // решает менеджер. Не камера, а плашка.
  if (stage.kind === 'camera' && blocked) {
    return (
      <main className="min-h-[80vh] p-3 flex flex-col justify-center gap-4">
        {closed ? <ClosedPlate /> : <WaitManagerPlate />}
        <button
          type="button"
          onClick={toMine}
          className={`${SECONDARY_BTN} border-2 border-gray-400 bg-white dark:bg-gray-900 text-gray-800 dark:text-gray-100`}
        >
          <Home size={26} aria-hidden /> {t('twa.simple.done.toMine')}
        </button>
      </main>
    )
  }

  if (stage.kind === 'camera' && !settled) return <main className="p-3"><Loading /></main>

  return (
    <main className="min-h-screen p-3 pb-[calc(12px+env(safe-area-inset-bottom))] flex flex-col gap-4">
      {input}
      {(stage.kind === 'camera' || stage.kind === 'processing') && (
        <div className="flex-1 flex flex-col items-center justify-center gap-6 py-10 text-center">
          <Camera size={96} className="text-gray-500" aria-hidden />
          <p className="text-[24px] font-bold">{t('twa.simple.done.shoot')}</p>
          <button
            type="button"
            disabled={stage.kind === 'processing'}
            onClick={openCamera}
            className={`${PRIMARY_BTN} bg-emerald-600 text-white`}
          >
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
              onClick={() => stage.kind === 'preview' && void send(stage.photo, stage.url)}
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
