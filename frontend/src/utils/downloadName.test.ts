import { describe, expect, it } from 'vitest'
import { downloadName } from './downloadName'

describe('downloadName (A10-FE-04)', () => {
  it('derives the extension from the response MIME, not from the uploader-supplied name', () => {
    expect(downloadName(7, 'application/pdf')).toBe('document-7.pdf')
    expect(downloadName(7, 'image/jpeg; charset=binary')).toBe('document-7.jpg')
  })

  it('falls back to a bare name for unknown MIME types', () => {
    expect(downloadName(7, 'application/octet-stream')).toBe('document-7')
  })
})
