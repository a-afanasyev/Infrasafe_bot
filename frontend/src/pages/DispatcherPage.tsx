import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import type { TFunction } from 'i18next'
import { AlertTriangle, CheckCircle2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { safeErrorMessage } from '@/utils/errorMessage'
import LanguageSwitcher from '../components/shared/LanguageSwitcher'
import { CATEGORIES, URGENCIES } from '../constants'
import { tCategory } from '../i18n/apiMaps'
import { useAuthStore } from '../stores/authStore'
import { usePageTitle } from '../hooks/usePageTitle'
import { useBuildings, useYards } from '../hooks/useAddresses'
import { useElevatorsForBuilding } from '../hooks/useElevators'
import {
  callCenterResidentApartments,
  checkCallCenterRequest,
  createDispatchRequest,
  searchCallCenterResidents,
  useCallCenterApartments,
  useCallCenterCapabilities,
  type CallCenterResident,
} from '../hooks/useCallCenter'
import type { AddressOption, CheckIssue, ResidentApartment } from '../twa/pages/dispatch/api'
import { EMPTY_ELEVATOR_SELECTION } from '../twa/components/elevatorSelection'
import {
  EMPTY_DRAFT,
  applyIssueFix,
  buildCheckBody,
  buildCreateBody,
  elevatorMissing,
  isPhoneComplete,
  needsElevator,
  residentQuery,
  withAddress,
  type Address,
  type Draft,
} from '../twa/pages/dispatch/model'

/** Выбор в трёх списках «двор → дом → квартира»; адрес заявки — самый глубокий выбранный. */
interface Picker {
  yardId: number | null
  buildingId: number | null
  apartmentId: number | null
}
const EMPTY_PICKER: Picker = { yardId: null, buildingId: null, apartmentId: null }
const BLANK: Draft = { ...EMPTY_DRAFT, urgency: 'low' }
type Phase = 'idle' | 'checking' | 'sending'

const parseId = (raw: string): number | null => (raw ? Number(raw) : null)
const issueKey = (i: CheckIssue): string => `${i.code}:${i.suggestion ?? ''}`
const urgencyLabel = (t: TFunction, urgency: string): string => t(`twa.create.urgency.${urgency}`)
/** Поле, к которому относится замечание без готовой подстановки. */
const FIELD_ID: Record<CheckIssue['field'], string> = {
  description: 'dw-description',
  category: 'dw-category',
  urgency: 'dw-urgency',
  address: 'dw-apartment',
}

function issueText(t: TFunction, issue: CheckIssue): string {
  const value =
    issue.field === 'category' && issue.suggestion
      ? tCategory(issue.suggestion, t)
      : issue.field === 'urgency' && issue.suggestion
        ? urgencyLabel(t, issue.suggestion)
        : undefined
  return t(`twa.dispatch.issue.${issue.code}`, { value, defaultValue: t('twa.dispatch.issue.generic') })
}

const SECTION = 'rounded-md border border-border-default bg-bg-card p-4 space-y-3'
const CHIP_ROW = 'flex flex-wrap gap-2'

/**
 * Веб-страница диспетчера: заявка по звонку целиком на одном экране. Та же
 * модель и те же запросы, что у экрана в Telegram (twa/pages/dispatch) —
 * отличается только раскладка: все поля сразу, без шагов.
 */
export default function DispatcherPage() {
  const { t } = useTranslation()
  usePageTitle(t('dispatchWeb.title'))
  const { user, logout } = useAuthStore()
  const [draft, setDraft] = useState<Draft>(BLANK)
  const [picker, setPicker] = useState<Picker>(EMPTY_PICKER)
  const [issues, setIssues] = useState<CheckIssue[]>([])
  // Что уже проверено и какие советы оставлены «как есть»: повторная отправка
  // без правок не зовёт ИИ снова.
  const [checkedKey, setCheckedKey] = useState<string | null>(null)
  const [kept, setKept] = useState<string[]>([])
  const [phase, setPhase] = useState<Phase>('idle')
  const [error, setError] = useState('')
  const [doneNumber, setDoneNumber] = useState<string | null>(null)
  const busy = phase !== 'idle'

  const caps = useCallCenterCapabilities(true)
  const yards = useYards()
  const buildings = useBuildings(picker.yardId)
  const apartments = useCallCenterApartments(picker.buildingId)
  const elevatorMode = needsElevator(draft)
  const elevators = useElevatorsForBuilding(elevatorMode ? (draft.address?.buildingId ?? null) : null)

  // Житель ищется сам, как только номер набран; поиск — удобство, не условие.
  const phoneKey = isPhoneComplete(draft.phone) ? residentQuery(draft.phone) : ''
  const matches = useQuery<CallCenterResident[]>({
    queryKey: ['callcenter-resident', phoneKey],
    queryFn: () => searchCallCenterResidents(phoneKey),
    enabled: phoneKey !== '',
    staleTime: 60_000,
    retry: false,
  })

  const patch = (p: Partial<Draft>) => setDraft((d) => ({ ...d, ...p }))
  const setAddress = (address: Address | null) =>
    setDraft((d) => ({ ...d, ...(address ? withAddress(d, address) : { address: null, elevator: EMPTY_ELEVATOR_SELECTION }) }))

  const pickResident = async (m: CallCenterResident) => {
    if (draft.resident?.id === m.id) {
      patch({ resident: null, residentApartments: [] })
      return
    }
    const list = await callCenterResidentApartments(m.id).catch((): ResidentApartment[] => [])
    patch({ resident: { id: m.id, fullName: m.full_name?.trim() || draft.phone }, residentApartments: list, callerName: '' })
  }

  const pick = (next: Picker) => {
    setPicker(next)
    const yard = yards.data?.find((y) => y.id === next.yardId)
    const building = buildings.data?.find((b) => b.id === next.buildingId)
    const apartment = apartments.data?.find((a) => a.id === next.apartmentId)
    if (building && apartment) {
      const label = `${building.address}, ${t('twa.dispatch.address.apartmentN', { number: apartment.number })}`
      setAddress({ level: 'apartment', id: apartment.id, label, buildingId: building.id })
    } else if (building) {
      setAddress({ level: 'building', id: building.id, label: building.address, buildingId: building.id })
    } else {
      setAddress(yard ? { level: 'yard', id: yard.id, label: yard.name, buildingId: null } : null)
    }
  }

  const pickResidentApartment = (a: ResidentApartment) => {
    setPicker(EMPTY_PICKER)
    setAddress({ level: 'apartment', id: a.id, label: a.label, buildingId: a.building_id })
  }

  const contentKey = JSON.stringify(buildCheckBody(draft))
  const visibleIssues = checkedKey === contentKey ? issues : []
  const ready =
    isPhoneComplete(draft.phone) && draft.address !== null && draft.category !== '' &&
    draft.description.trim() !== '' && !elevatorMissing(draft)

  const fix = (issue: CheckIssue, option?: AddressOption) => {
    const fixed = applyIssueFix(draft, issue, option)
    if (fixed === draft) {
      document.getElementById(FIELD_ID[issue.field])?.focus() // подставить нечего — к самому полю
      return
    }
    if (option) setPicker({ yardId: option.yard_id, buildingId: option.type === 'building' ? option.id : null, apartmentId: null })
    setDraft(fixed)
    setCheckedKey(JSON.stringify(buildCheckBody(fixed)))
    setIssues((list) => list.filter((i) => i.code !== issue.code))
  }

  const keep = (issue: CheckIssue) => {
    setKept((k) => [...k, issueKey(issue)])
    setIssues((list) => list.filter((i) => i.code !== issue.code))
  }

  const submit = async () => {
    setError('')
    if (caps.data?.address_suggest && checkedKey !== contentKey) {
      setPhase('checking')
      // Сбой проверки не должен останавливать приём звонка.
      const result = await checkCallCenterRequest(buildCheckBody(draft)).catch(() => null)
      const fresh = (result?.issues ?? []).filter((i) => !kept.includes(issueKey(i)))
      setCheckedKey(contentKey)
      setIssues(fresh)
      if (fresh.length > 0) {
        setPhase('idle')
        return
      }
    }
    setPhase('sending')
    try {
      const created = await createDispatchRequest(buildCreateBody(draft))
      setDoneNumber(created.request_number)
      setDraft(BLANK)
      setPicker(EMPTY_PICKER)
      setIssues([])
      setCheckedKey(null)
      setKept([])
      document.getElementById('dw-phone')?.focus()
    } catch (e: unknown) {
      setError(safeErrorMessage(e, t('errors.createRequest')))
    } finally {
      setPhase('idle')
    }
  }

  const found = matches.data ?? []

  return (
    <div className="min-h-screen bg-bg-primary text-text-primary">
      <header className="flex items-center justify-between border-b border-border-default px-4 py-3">
        <h1 className="text-lg font-semibold">{t('dispatchWeb.title')}</h1>
        <div className="flex items-center gap-3 text-sm text-text-muted">
          <span>{user?.first_name}</span>
          <LanguageSwitcher />
          <Button variant="outline" size="sm" onClick={() => logout()}>{t('common.logout')}</Button>
        </div>
      </header>

      <main className="mx-auto max-w-3xl space-y-4 p-4">
        {doneNumber && (
          <p role="status" className="flex items-center gap-2 rounded-md border border-accent bg-accent-dim p-3 text-base font-semibold">
            <CheckCircle2 size={22} className="text-accent" aria-hidden />
            {t('twa.dispatch.done.title', { number: doneNumber })}
          </p>
        )}

        <section className={SECTION}>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="dw-phone">{t('twa.dispatch.phone.title')} *</Label>
              <Input
                id="dw-phone"
                type="tel"
                autoFocus
                autoComplete="off"
                maxLength={20}
                placeholder="90 123 45 67"
                value={draft.phone}
                onChange={(e) => {
                  setDoneNumber(null)
                  patch({ phone: e.target.value, resident: null, residentApartments: [] })
                }}
              />
            </div>
            {!draft.resident && (
              <div className="space-y-1.5">
                <Label htmlFor="dw-name">{t('twa.dispatch.name.title')}</Label>
                <Input
                  id="dw-name"
                  maxLength={100}
                  placeholder={t('twa.dispatch.name.hint')}
                  value={draft.callerName}
                  onChange={(e) => patch({ callerName: e.target.value })}
                />
              </div>
            )}
          </div>
          {found.length > 0 && (
            <div className="space-y-1.5">
              <p className="text-sm text-text-muted">{t('dispatchWeb.residentFound')}</p>
              <div className={CHIP_ROW}>
                {found.map((m) => (
                  <Button
                    key={m.id}
                    type="button"
                    variant={draft.resident?.id === m.id ? 'default' : 'outline'}
                    aria-pressed={draft.resident?.id === m.id}
                    onClick={() => pickResident(m)}
                  >
                    {m.full_name?.trim() || m.phone}
                  </Button>
                ))}
              </div>
            </div>
          )}
        </section>

        <section className={SECTION}>
          {draft.resident && draft.residentApartments.length > 0 && (
            <div className="space-y-1.5">
              <p className="text-sm text-text-muted">
                {t('twa.dispatch.address.residentApartments', { name: draft.resident.fullName })}
              </p>
              <div className={CHIP_ROW}>
                {draft.residentApartments.map((a) => {
                  const chosen = draft.address?.level === 'apartment' && draft.address.id === a.id
                  return (
                    <Button key={a.id} type="button" variant={chosen ? 'default' : 'outline'} aria-pressed={chosen} onClick={() => pickResidentApartment(a)}>
                      {a.label}
                    </Button>
                  )
                })}
              </div>
            </div>
          )}
          <div className="grid gap-3 sm:grid-cols-3">
            <div className="space-y-1.5">
              <Label htmlFor="dw-yard">{t('dispatchWeb.yard')} *</Label>
              <Select id="dw-yard" value={picker.yardId ?? ''} onChange={(e) => pick({ yardId: parseId(e.target.value), buildingId: null, apartmentId: null })}>
                <option value="">{t('twa.dispatch.address.yard')}</option>
                {(yards.data ?? []).map((y) => <option key={y.id} value={y.id}>{y.name}</option>)}
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="dw-building">{t('dispatchWeb.building')}</Label>
              <Select id="dw-building" value={picker.buildingId ?? ''} disabled={picker.yardId === null} onChange={(e) => pick({ ...picker, buildingId: parseId(e.target.value), apartmentId: null })}>
                <option value="">{t('dispatchWeb.wholeYard')}</option>
                {(buildings.data ?? []).map((b) => <option key={b.id} value={b.id}>{b.address}</option>)}
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="dw-apartment">{t('dispatchWeb.apartment')}</Label>
              <Select id="dw-apartment" value={picker.apartmentId ?? ''} disabled={picker.buildingId === null} onChange={(e) => pick({ ...picker, apartmentId: parseId(e.target.value) })}>
                <option value="">{t('dispatchWeb.wholeBuilding')}</option>
                {(apartments.data ?? []).map((a) => <option key={a.id} value={a.id}>{a.number}</option>)}
              </Select>
            </div>
          </div>
          <p className="text-sm">
            <span className="text-text-muted">{t('twa.dispatch.review.address')}: </span>
            <span className="font-semibold">{draft.address?.label ?? t('dispatchWeb.addressMissing')}</span>
          </p>
        </section>

        <section className={SECTION}>
          <div className="space-y-1.5">
            <Label htmlFor="dw-category">{t('twa.dispatch.category.title')} *</Label>
            <div id="dw-category" tabIndex={-1} className={CHIP_ROW}>
              {CATEGORIES.map((c) => (
                <Button key={c} type="button" variant={draft.category === c ? 'default' : 'outline'} aria-pressed={draft.category === c} onClick={() => patch({ category: c })}>
                  {tCategory(c, t)}
                </Button>
              ))}
            </div>
          </div>

          {elevatorMode && (draft.address?.buildingId == null ? (
            <p className="text-sm text-red">{t('dispatchWeb.elevatorNeedsBuilding')}</p>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="dw-elevator">{t('callcenter.elevator.elevator')}</Label>
                <Select
                  id="dw-elevator"
                  value={draft.elevator.elevatorId ?? ''}
                  onChange={(e) => {
                    const el = elevators.data?.find((x) => x.id === parseId(e.target.value))
                    patch({ elevator: { ...draft.elevator, elevatorId: el?.id ?? null, elevatorLabel: el?.label ?? '', elevatorStatus: el?.current_status ?? null } })
                  }}
                >
                  <option value="">
                    {t(elevators.isSuccess && elevators.data.length === 0 ? 'callcenter.elevator.noElevators' : 'callcenter.elevator.elevatorPlaceholder')}
                  </option>
                  {(elevators.data ?? []).map((el) => <option key={el.id} value={el.id}>{el.label}</option>)}
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label>{t('callcenter.elevator.operational')}</Label>
                <div className={CHIP_ROW}>
                  {([true, false] as const).map((v) => (
                    <Button key={String(v)} type="button" variant={draft.elevator.operational === v ? 'default' : 'outline'} aria-pressed={draft.elevator.operational === v} onClick={() => patch({ elevator: { ...draft.elevator, operational: v } })}>
                      {t(v ? 'callcenter.elevator.yes' : 'callcenter.elevator.no')}
                    </Button>
                  ))}
                </div>
              </div>
            </div>
          ))}

          <div className="space-y-1.5">
            <Label htmlFor="dw-description">{t('twa.dispatch.description.title')} *</Label>
            <Textarea
              id="dw-description"
              rows={3}
              placeholder={t('twa.dispatch.description.hint')}
              value={draft.description}
              onChange={(e) => patch({ description: e.target.value })}
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="dw-urgency">{t('twa.dispatch.urgency.title')}</Label>
            <div id="dw-urgency" tabIndex={-1} className={CHIP_ROW}>
              {URGENCIES.map((u) => (
                <Button key={u} type="button" variant={draft.urgency === u ? 'default' : 'outline'} aria-pressed={draft.urgency === u} onClick={() => patch({ urgency: u })}>
                  {urgencyLabel(t, u)}
                </Button>
              ))}
            </div>
          </div>
        </section>

        {visibleIssues.map((issue) => (
          <div key={issue.code} role="alert" className="space-y-2 rounded-md border-2 border-amber-500 bg-amber-500/10 p-3">
            <p className="flex gap-2 font-semibold">
              <AlertTriangle size={20} className="shrink-0 text-amber-500" aria-hidden />
              {issueText(t, issue)}
            </p>
            <div className={CHIP_ROW}>
              {issue.options.map((o) => (
                <Button key={`${o.type}-${o.id}`} type="button" disabled={busy} onClick={() => fix(issue, o)}>{o.label}</Button>
              ))}
              {issue.options.length === 0 && (
                <Button type="button" disabled={busy} onClick={() => fix(issue)}>{t('twa.dispatch.issue.fix')}</Button>
              )}
              <Button type="button" variant="outline" disabled={busy} onClick={() => keep(issue)}>{t('twa.dispatch.issue.keep')}</Button>
            </div>
          </div>
        ))}

        {error && <p role="alert" className="text-sm text-red">{error}</p>}

        <Button size="lg" className="w-full" disabled={busy || !ready} onClick={submit}>
          {phase === 'checking'
            ? t('twa.dispatch.review.checking')
            : phase === 'sending'
              ? t('twa.dispatch.review.sending')
              : t(visibleIssues.length > 0 ? 'twa.dispatch.review.sendAnyway' : 'twa.dispatch.review.send')}
        </Button>
      </main>
    </div>
  )
}
