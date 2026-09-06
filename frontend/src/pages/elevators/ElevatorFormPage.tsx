import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { useTranslation } from 'react-i18next'
import { useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { ArrowLeft, Copy } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { usePageTitle } from '../../hooks/usePageTitle'
import {
  elevatorKeys,
  fetchElevator,
  useApiLang,
  useCreateElevator,
  useElevator,
  useElevators,
  usePatchElevator,
} from '../../hooks/useElevators'
import LoadingSpinner from '../../components/shared/LoadingSpinner'
import EmptyState from '../../components/shared/EmptyState'
import ElevatorFormFields from '../../components/elevators/ElevatorFormFields'
import {
  EMPTY_ELEVATOR_FORM,
  copyPassportFrom,
  formFromDetail,
  toCreatePayload,
  toPatchPayload,
  validateElevatorForm,
  type ElevatorFormError,
  type ElevatorFormState,
} from '../../utils/elevatorForm'
import type { ElevatorDetail } from '../../types/elevators'

/**
 * Создание (/dashboard/elevators/new) и правка (/dashboard/elevators/:id/edit)
 * лифта. Только manager (кнопки входа скрыты по роли; API гейтит сам).
 * «Скопировать предыдущий» — паспортные/договорные поля последнего созданного
 * лифта (max id из списка), кроме номера/серийника/паспорта/подъезда.
 * PATCH несёт expected_version; 409 → toast (хук).
 *
 * Сид формы из карточки — ОДИН раз. Фоновый рефетч (staleTime/фокус окна)
 * приносит новый объект `detail.data` с тем же `version` — ввод не трогаем;
 * если `version` вырос (кто-то сохранил карточку), пересиживаем и предупреждаем.
 */
export default function ElevatorFormPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const lang = useApiLang()
  const { id: idParam } = useParams<{ id: string }>()
  const editId = idParam !== undefined ? Number(idParam) : null
  const isEdit = editId !== null && Number.isFinite(editId)
  usePageTitle(t(isEdit ? 'elevators.form.editTitle' : 'elevators.form.createTitle'))

  const detail = useElevator(isEdit ? editId : null)
  // Кандидаты для «Скопировать предыдущий» — только в режиме создания.
  const latest = useElevators({ limit: 200, include_archived: false }, !isEdit)
  const create = useCreateElevator()
  const patch = usePatchElevator(editId ?? 0)

  const [form, setForm] = useState<ElevatorFormState>(EMPTY_ELEVATOR_FORM)
  const [error, setError] = useState<ElevatorFormError | null>(null)
  const [copying, setCopying] = useState(false)

  const [seededVersion, setSeededVersion] = useState<number | null>(null)
  if (isEdit && detail.data && detail.data.version !== seededVersion) {
    const firstSeed = seededVersion === null
    setSeededVersion(detail.data.version)
    setForm(formFromDetail(detail.data))
    if (!firstSeed) toast.info(t('elevators.form.reloaded'))
  }

  const patchForm = (p: Partial<ElevatorFormState>) => setForm((prev) => ({ ...prev, ...p }))

  const copyPrevious = async () => {
    const items = latest.data?.items ?? []
    if (items.length === 0) {
      toast.info(t('elevators.form.copyNone'))
      return
    }
    const source = items.reduce((max, it) => (it.id > max.id ? it : max), items[0])
    setCopying(true)
    try {
      const full = await queryClient.fetchQuery<ElevatorDetail>({
        queryKey: [...elevatorKeys.detail(source.id), lang],
        queryFn: () => fetchElevator(source.id, lang),
      })
      setForm((prev) => copyPassportFrom(prev, full))
      toast.success(t('elevators.form.copied', { label: full.label }))
    } catch {
      toast.error(t('common.error'))
    } finally {
      setCopying(false)
    }
  }

  const submit = () => {
    const err = validateElevatorForm(form)
    setError(err)
    if (err) return
    if (isEdit && detail.data) {
      patch.mutate(toPatchPayload(form, detail.data.version), {
        onSuccess: () => navigate(`/dashboard/elevators/${editId}`),
      })
    } else {
      create.mutate(toCreatePayload(form), {
        onSuccess: (created) => navigate(`/dashboard/elevators/${created.id}`),
      })
    }
  }

  if (isEdit && detail.isLoading) return <LoadingSpinner />
  if (isEdit && (detail.isError || !detail.data)) {
    return (
      <div className="p-6">
        <EmptyState icon="🛗" title={t('elevators.detail.notFound')} />
      </div>
    )
  }

  const pending = create.isPending || patch.isPending
  const backTo = isEdit ? `/dashboard/elevators/${editId}` : '/dashboard/elevators'

  return (
    <div className="p-6 flex flex-col gap-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <Button asChild variant="outline" size="sm">
            <Link to={backTo} aria-label={t('common.back')}><ArrowLeft size={15} /></Link>
          </Button>
          <h1 className="text-xl font-semibold text-text-primary">
            {t(isEdit ? 'elevators.form.editTitle' : 'elevators.form.createTitle')}
            {isEdit && detail.data ? ` · ${detail.data.label}` : ''}
          </h1>
        </div>
        {!isEdit && (
          <Button variant="outline" size="sm" onClick={copyPrevious} disabled={copying || latest.isLoading}>
            <Copy size={15} /> {t('elevators.actions.copyPrevious')}
          </Button>
        )}
      </div>

      <ElevatorFormFields form={form} onChange={patchForm} />

      {error && <p role="alert" className="text-[13px] text-red">{t(`elevators.form.${error}`)}</p>}

      <div className="flex items-center gap-2">
        <Button onClick={submit} disabled={pending}>
          {pending ? t('common.saving') : isEdit ? t('common.save') : t('common.create')}
        </Button>
        <Button asChild variant="outline">
          <Link to={backTo}>{t('common.cancel')}</Link>
        </Button>
      </div>
    </div>
  )
}
