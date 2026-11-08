import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { usePersonName } from '../../hooks/usePersonName'
import {
  searchCallCenterResidents,
  suggestCallCenterAddress,
  useCallCenterCapabilities,
  useCreateCallCenterRequest,
  type AddressOption,
  type CallCenterBody,
  type CallCenterResident,
} from '../../hooks/useCallCenter'
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
import { safeErrorMessage } from '@/utils/errorMessage'
import { isElevatorsEnabled } from '../../utils/featureFlags'
import CallCenterElevatorFields from './CallCenterElevatorFields'
import AddressLevelPicker from '../addresses/AddressLevelPicker'
import { addressLevelBody, EMPTY_ADDRESS_LEVEL, type AddressLevelValue } from '../addresses/addressLevel'
import { EMPTY_ELEVATOR_VALUE, isElevatorValueComplete, type CallCenterElevatorValue } from './callCenterElevator'

interface Props { isOpen: boolean; onClose: () => void }

import { CATEGORIES, URGENCIES } from '../../constants'

const INITIAL_FORM = { category: '', urgency: 'low', description: '' }

export default function CallCenterModal({ isOpen, onClose }: Props) {
  const { t } = useTranslation()
  const { name: personName } = usePersonName()
  const [query, setQuery] = useState('')
  const [residents, setResidents] = useState<CallCenterResident[]>([])
  const [selected, setSelected] = useState<number | null>(null)
  const [form, setForm] = useState(INITIAL_FORM)
  const [elevator, setElevator] = useState<CallCenterElevatorValue>(EMPTY_ELEVATOR_VALUE)
  // Адрес — только из справочника (решение владельца 2026-11-07).
  const [address, setAddress] = useState<AddressLevelValue>(EMPTY_ADDRESS_LEVEL)
  // Свободный ввод при включённом ИИ: слова звонящего → варианты справочника.
  const caps = useCallCenterCapabilities(isOpen)
  const [addressText, setAddressText] = useState('')
  const [suggestions, setSuggestions] = useState<AddressOption[] | null>(null)
  const [suggesting, setSuggesting] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const createRequest = useCreateCallCenterRequest()

  // Категория «Лифт» при включённом модуле: адрес — дом из справочника
  // (building_id), плюс лифт и «работает?»; свободный текст адреса скрыт —
  // к legacy-адресу лифт не привязать (T6).
  const elevatorMode = form.category === 'elevator' && isElevatorsEnabled()

  useEffect(() => {
    if (isOpen) {
      setQuery('')
      setResidents([])
      setSelected(null)
      setForm(INITIAL_FORM)
      setElevator(EMPTY_ELEVATOR_VALUE)
      setAddress(EMPTY_ADDRESS_LEVEL)
      setAddressText('')
      setSuggestions(null)
      setError('')
    }
  }, [isOpen])

  const search = async () => {
    try {
      setResidents(await searchCallCenterResidents(query))
    } catch {
      setError(t('errors.searchResident'))
    }
  }

  const addressBody = addressLevelBody(address)
  const canSubmit = elevatorMode ? isElevatorValueComplete(elevator) : addressBody !== null

  const buildBody = (): CallCenterBody => {
    const base: CallCenterBody = { category: form.category, urgency: form.urgency, description: form.description, user_id: selected || undefined }
    if (!elevatorMode) return { ...base, ...addressBody, address_text: addressText.trim() || undefined }
    return {
      ...base,
      building_id: elevator.buildingId,
      elevator_id: elevator.elevatorId,
      elevator_operational: elevator.operational,
    }
  }

  const suggest = async () => {
    setSuggesting(true)
    setError('')
    try {
      const res = await suggestCallCenterAddress(addressText.trim(), form.description)
      setSuggestions(res.options)
      // Категорию/срочность ИИ подставляем только в нетронутые поля.
      if (res.category && !form.category) setForm(f => ({ ...f, category: res.category as string }))
      if (res.urgency && form.urgency === INITIAL_FORM.urgency) setForm(f => ({ ...f, urgency: res.urgency as string }))
      if (res.options.length === 1) applySuggestion(res.options[0])
    } catch (e: unknown) {
      setError(safeErrorMessage(e, t('callcenter.suggest.failed')))
    } finally {
      setSuggesting(false)
    }
  }

  const applySuggestion = (o: AddressOption) =>
    setAddress({ yardId: o.yard_id, buildingId: o.type === 'building' ? o.id : null, apartmentId: null })

  const submit = async () => {
    if (!canSubmit) {
      setError(t(elevatorMode ? 'callcenter.elevator.required' : 'addressPicker.required'))
      return
    }
    setLoading(true)
    setError('')
    try {
      await createRequest.mutateAsync(buildBody())
      onClose()
    } catch (e: unknown) {
      // 422 от сервера (в т.ч. Р11: лифт обязателен) — detail строкой или
      // pydantic-списком; safeErrorMessage не даёт уронить рендер объектом.
      setError(safeErrorMessage(e, t('errors.createRequest')))
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
                <span className="font-medium text-text-primary">{personName(r.full_name)}</span>
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

        {/* Адрес (обязателен, из справочника): для «Лифта» — дом/лифт/работает */}
        {elevatorMode ? (
          <CallCenterElevatorFields value={elevator} onChange={setElevator} />
        ) : (
          <>
            {caps.data?.address_suggest && (
              <div className="space-y-1.5">
                <Label htmlFor="cc-address-text">{t('callcenter.suggest.label')}</Label>
                <div className="flex gap-2">
                  <Input
                    id="cc-address-text"
                    className="flex-1"
                    placeholder={t('callcenter.suggest.placeholder')}
                    value={addressText}
                    onChange={(e) => setAddressText(e.target.value)}
                    onKeyDown={e => e.key === 'Enter' && addressText.trim().length >= 2 && suggest()}
                  />
                  <Button variant="outline" onClick={suggest} disabled={suggesting || addressText.trim().length < 2}>
                    {t(suggesting ? 'callcenter.suggest.loading' : 'callcenter.suggest.button')}
                  </Button>
                </div>
                {suggestions !== null && (suggestions.length === 0 ? (
                  <p className="text-text-muted text-xs">{t('callcenter.suggest.none')}</p>
                ) : (
                  <div className="flex flex-wrap gap-1.5">
                    {suggestions.map(o => {
                      const chosen = o.type === 'building' ? address.buildingId === o.id : address.yardId === o.id && address.buildingId === null
                      return (
                        <button
                          key={`${o.type}-${o.id}`}
                          type="button"
                          onClick={() => applySuggestion(o)}
                          className={cn(
                            'border rounded-sm px-2 py-1 text-xs transition-colors',
                            chosen ? 'border-accent bg-accent-dim' : 'border-border-default hover:bg-bg-surface',
                          )}
                        >
                          {o.label}
                        </button>
                      )
                    })}
                  </div>
                ))}
              </div>
            )}
            <AddressLevelPicker value={address} onChange={setAddress} idPrefix="cc" />
          </>
        )}

        {error && <p className="text-red text-sm">{error}</p>}

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>{t('common.cancel')}</Button>
          <Button
            onClick={submit}
            disabled={loading || !form.category || !form.description || !canSubmit}
          >
            {loading ? t('callcenter.submitLoading') : t('callcenter.submit')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
