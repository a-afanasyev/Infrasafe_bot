import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { apiClient } from '../../api/client'
import { useQueryClient } from '@tanstack/react-query'
import { tCategory, tUrgency } from '../../i18n/apiMaps'
import { cn } from '@/lib/utils'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'

interface Props { isOpen: boolean; onClose: () => void }

import { CATEGORIES, URGENCIES } from '../../constants'

const INITIAL_FORM = { category: '', urgency: 'Обычная', description: '', address: '' }

export default function CallCenterModal({ isOpen, onClose }: Props) {
  const { t } = useTranslation()
  const [query, setQuery] = useState('')
  const [residents, setResidents] = useState<Array<{ id: number; full_name: string; phone: string }>>([])
  const [selected, setSelected] = useState<number | null>(null)
  const [form, setForm] = useState(INITIAL_FORM)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const queryClient = useQueryClient()

  useEffect(() => {
    if (isOpen) {
      setQuery('')
      setResidents([])
      setSelected(null)
      setForm(INITIAL_FORM)
      setError('')
    }
  }, [isOpen])

  const search = async () => {
    try {
      const { data } = await apiClient.get('/api/v2/callcenter/search-resident', { params: { q: query } })
      setResidents(data)
    } catch {
      setError(t('errors.searchResident'))
    }
  }

  const submit = async () => {
    if (!form.address.trim()) {
      setError(t('errors.specifyAddress'))
      return
    }
    setLoading(true)
    setError('')
    try {
      await apiClient.post('/api/v2/callcenter/requests', {
        ...form,
        user_id: selected || undefined,
      })
      queryClient.invalidateQueries({ queryKey: ['kanban'] })
      onClose()
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(msg ?? t('errors.createRequest'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <Dialog open={isOpen} onOpenChange={(open) => { if (!open) onClose() }}>
      <DialogContent className="max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{t('callcenter.title')}</DialogTitle>
        </DialogHeader>

        {/* Resident search */}
        <div className="flex gap-2">
          <Input
            className="flex-1"
            placeholder={t('callcenter.searchPlaceholder')}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && search()}
          />
          <Button onClick={search}>{t('callcenter.find')}</Button>
        </div>

        {residents.length > 0 && (
          <div className="space-y-1">
            {residents.map((r) => (
              <div
                key={r.id}
                onClick={() => setSelected(r.id)}
                className={cn(
                  'border rounded-sm p-2 cursor-pointer text-sm transition-colors',
                  selected === r.id
                    ? 'border-accent bg-accent-dim'
                    : 'border-border-default hover:bg-bg-surface'
                )}
              >
                <span className="font-medium text-text-primary">{r.full_name}</span>
                <span className="text-text-muted"> &middot; {r.phone}</span>
              </div>
            ))}
          </div>
        )}

        {/* Category */}
        <div className="space-y-1.5">
          <Label htmlFor="cc-category">{t('callcenter.categoryLabel')}</Label>
          <Select
            id="cc-category"
            value={form.category}
            onChange={(e) => setForm({ ...form, category: e.target.value })}
          >
            <option value="">{t('callcenter.categoryPlaceholder')}</option>
            {CATEGORIES.map(c => <option key={c} value={c}>{tCategory(c, t)}</option>)}
          </Select>
        </div>

        {/* Urgency */}
        <div className="space-y-1.5">
          <Label htmlFor="cc-urgency">{t('callcenter.urgencyLabel')}</Label>
          <Select
            id="cc-urgency"
            value={form.urgency}
            onChange={(e) => setForm({ ...form, urgency: e.target.value })}
          >
            {URGENCIES.map(u => <option key={u} value={u}>{tUrgency(u, t)}</option>)}
          </Select>
        </div>

        {/* Description */}
        <div className="space-y-1.5">
          <Label htmlFor="cc-desc">{t('callcenter.descriptionLabel')}</Label>
          <Textarea
            id="cc-desc"
            rows={3}
            placeholder={t('callcenter.descriptionPlaceholder')}
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
          />
        </div>

        {/* Address (required) */}
        <div className="space-y-1.5">
          <Label htmlFor="cc-address">{t('callcenter.addressLabel')}</Label>
          <Input
            id="cc-address"
            placeholder={t('callcenter.addressPlaceholder')}
            value={form.address}
            onChange={(e) => setForm({ ...form, address: e.target.value })}
          />
        </div>

        {error && <p className="text-red text-sm">{error}</p>}

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>{t('common.cancel')}</Button>
          <Button
            onClick={submit}
            disabled={loading || !form.category || !form.description || !form.address.trim()}
          >
            {loading ? t('callcenter.submitLoading') : t('callcenter.submit')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
