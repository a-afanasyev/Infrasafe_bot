import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { X } from 'lucide-react'
import { downscaleImage } from '../utils/downscaleImage'
import type { CameraSource } from './queue'

/**
 * Камера внутри приложения: живой поток → кадр. Выбора файла здесь нет вовсе —
 * старое фото из галереи приложить нечем.
 *
 * Если поток недоступен (нет разрешения, старый WebView), остаётся системная
 * камера (`capture`). На части телефонов она пускает в галерею, поэтому такой
 * кадр помечается `system` и сервер не даёт ему уровень доверия «live».
 */
const MAX_SIDE = 1280
const JPEG_QUALITY = 0.82

interface Props {
  title: string
  subtitle: string
  onShot: (photo: Blob, source: CameraSource) => void
  onClose: () => void
}

function frameToBlob(video: HTMLVideoElement): Promise<Blob | null> {
  const scale = Math.min(1, MAX_SIDE / Math.max(video.videoWidth, video.videoHeight))
  const canvas = document.createElement('canvas')
  canvas.width = Math.round(video.videoWidth * scale)
  canvas.height = Math.round(video.videoHeight * scale)
  canvas.getContext('2d')?.drawImage(video, 0, 0, canvas.width, canvas.height)
  return new Promise((resolve) => canvas.toBlob(resolve, 'image/jpeg', JPEG_QUALITY))
}

export default function LiveCamera({ title, subtitle, onShot, onClose }: Props) {
  const { t } = useTranslation()
  const videoRef = useRef<HTMLVideoElement>(null)
  const [mode, setMode] = useState<'starting' | 'live' | 'system'>(
    () => (typeof navigator.mediaDevices?.getUserMedia === 'function' ? 'starting' : 'system'),
  )

  useEffect(() => {
    let stream: MediaStream | null = null
    let cancelled = false
    const media = navigator.mediaDevices
    if (!media?.getUserMedia) return
    media.getUserMedia({ video: { facingMode: { ideal: 'environment' } }, audio: false }).then(
      (s) => {
        if (cancelled) {
          s.getTracks().forEach((track) => track.stop())
          return
        }
        stream = s
        if (videoRef.current) videoRef.current.srcObject = s
        setMode('live')
      },
      () => { if (!cancelled) setMode('system') },
    )
    return () => {
      cancelled = true
      stream?.getTracks().forEach((track) => track.stop())
    }
  }, [])

  const shoot = async () => {
    const video = videoRef.current
    if (!video || video.videoWidth === 0) return
    const blob = await frameToBlob(video)
    if (blob) onShot(blob, 'live')
  }

  const pickSystem = async (file: File | undefined) => {
    if (file) onShot(await downscaleImage(file, { maxDimension: MAX_SIDE }), 'system')
  }

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-black text-white" role="dialog" aria-label={title}>
      <div className="flex items-center gap-3 p-4">
        <button type="button" onClick={onClose} aria-label={t('twa.cleaning.camera.close')} className="flex h-12 w-12 items-center justify-center rounded-full bg-gray-800">
          <X size={26} aria-hidden />
        </button>
        <div>
          <p className="text-[20px] font-bold">{title}</p>
          <p className="text-[16px] text-gray-300">{subtitle}</p>
        </div>
      </div>
      <div className="relative mx-3 flex flex-1 items-center justify-center overflow-hidden rounded-2xl bg-gray-800">
        <video ref={videoRef} autoPlay playsInline muted className={mode === 'live' ? 'h-full w-full object-cover' : 'hidden'} />
        {mode === 'starting' && <p className="text-[18px] text-gray-300">{t('twa.cleaning.camera.starting')}</p>}
        {mode === 'system' && <p className="px-8 text-center text-[18px] text-gray-200">{t('twa.cleaning.camera.systemHint')}</p>}
      </div>
      <p className="px-4 pt-3 text-center text-[16px] text-gray-300">{t('twa.cleaning.camera.note')}</p>
      <div className="flex items-center justify-center p-5">
        {mode === 'system' ? (
          <label className="flex h-[72px] w-full cursor-pointer items-center justify-center rounded-2xl bg-emerald-600 text-[22px] font-bold">
            {t('twa.cleaning.camera.openSystem')}
            <input type="file" accept="image/*" capture="environment" className="sr-only" onChange={(e) => void pickSystem(e.target.files?.[0])} />
          </label>
        ) : (
          <button
            type="button" onClick={() => void shoot()} disabled={mode !== 'live'} aria-label={t('twa.cleaning.camera.shoot')}
            className="flex h-[88px] w-[88px] items-center justify-center rounded-full border-[5px] border-white disabled:opacity-40"
          >
            <span className="block h-[66px] w-[66px] rounded-full bg-white" />
          </button>
        )}
      </div>
    </div>
  )
}
