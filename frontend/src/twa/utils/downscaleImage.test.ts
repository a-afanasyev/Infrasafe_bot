import { describe, it, expect, vi, afterEach } from 'vitest'
import { downscaleImage } from './downscaleImage'

// Регрессия прод-инцидента 2026-07-25 (profk): фото 13.4 МБ с iPhone отбивалось
// 413 на edge-nginx (client_max_body_size 10M) ДО нашего API — заявка создавалась,
// а загрузка фото залипала. jsdom не умеет ни декодировать изображения, ни
// canvas.toBlob, поэтому нужные примитивы подменяем.

function makeFile(size: number, type = 'image/jpeg', name = 'IMG_5090.HEIC'): File {
  const f = new File([new Uint8Array(1)], name, { type })
  // Настоящий буфер на 13 МБ в тесте не нужен — важен только заявленный size.
  Object.defineProperty(f, 'size', { value: size })
  return f
}

/** Успешный путь сжатия: FileReader → Image.onload → canvas.toBlob. */
function stubCanvasPipeline({ outSize }: { outSize: number }) {
  vi.spyOn(FileReader.prototype, 'readAsDataURL').mockImplementation(function (
    this: FileReader,
  ) {
    Object.defineProperty(this, 'result', { value: 'data:image/jpeg;base64,AAA', writable: true })
    this.onload?.({} as ProgressEvent<FileReader>)
  })
  Object.defineProperty(Image.prototype, 'src', {
    configurable: true,
    set(this: HTMLImageElement) {
      Object.defineProperty(this, 'width', { value: 4032, configurable: true })
      Object.defineProperty(this, 'height', { value: 3024, configurable: true })
      setTimeout(() => this.onload?.(new Event('load') as never), 0)
    },
  })
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({
    drawImage: vi.fn(),
  } as unknown as CanvasRenderingContext2D)
  vi.spyOn(HTMLCanvasElement.prototype, 'toBlob').mockImplementation((cb) =>
    cb(new Blob([new Uint8Array(1)], { type: 'image/jpeg' }) as Blob & { size: number }),
  )
  // Blob в jsdom считает размер по содержимому — подменяем на ожидаемый.
  vi.spyOn(Blob.prototype, 'size', 'get').mockReturnValue(outSize)
}

afterEach(() => {
  vi.restoreAllMocks()
})

describe('downscaleImage', () => {
  it('сжимает крупное фото и отдаёт JPEG', async () => {
    stubCanvasPipeline({ outSize: 400_000 })
    const out = await downscaleImage(makeFile(13_388_711))

    expect(out.type).toBe('image/jpeg')
    expect(out.size).toBe(400_000)
    // HEIC с iPhone media-service отклонил бы по ALLOWED_FILE_TYPES — canvas
    // всегда отдаёт JPEG, поэтому и расширение меняем.
    expect(out.name).toBe('IMG_5090.jpg')
  })

  it('не трогает файл ниже порога — незачем терять качество', async () => {
    const small = makeFile(900_000)
    expect(await downscaleImage(small)).toBe(small)
  })

  it('не трогает видео', async () => {
    const video = makeFile(20_000_000, 'video/mp4', 'clip.mp4')
    expect(await downscaleImage(video)).toBe(video)
  })

  it('возвращает оригинал, если сжатие вышло не меньше исходного', async () => {
    stubCanvasPipeline({ outSize: 20_000_000 })
    const original = makeFile(13_388_711)
    expect(await downscaleImage(original)).toBe(original)
  })

  it('возвращает оригинал при ошибке декодирования, а не бросает', async () => {
    vi.spyOn(FileReader.prototype, 'readAsDataURL').mockImplementation(function (
      this: FileReader,
    ) {
      this.onerror?.({} as ProgressEvent<FileReader>)
    })
    const original = makeFile(13_388_711)
    expect(await downscaleImage(original)).toBe(original)
  })
})
