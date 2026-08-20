import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { MAX_FULL_NAME_LEN, normalizeFullName, validateFullName } from '@/utils/personName'

interface Props {
  /** Текущее ФИО; пустая строка — «не указано». */
  currentName: string
  isPending: boolean
  /** Родитель владеет мутацией: инвалидация кэшей у разделов разная. */
  onSubmit: (fullName: string) => void
  onClose: () => void
}

/**
 * Исправление ФИО жителя или сотрудника менеджером.
 *
 * Поле одно, а не «Имя» + «Фамилия»: ФИО и вводится одной строкой (регистрация
 * жителя, бот), и хранится как одна строка, разложенная по двум историческим
 * колонкам. Два поля заставили бы менеджера угадывать, какая половина куда
 * попала при регистрации.
 */
export default function EditFullNameModal({ currentName, isPending, onSubmit, onClose }: Props) {
  const { t } = useTranslation()
  const [value, setValue] = useState(currentName)
  const [touched, setTouched] = useState(false)

  const error = validateFullName(value)
  const normalized = normalizeFullName(value)
  const unchanged = normalized === normalizeFullName(currentName)
  const disabled = isPending || error !== null || unchanged

  const submit = () => {
    setTouched(true)
    if (disabled) return
    onSubmit(normalized)
  }

  return (
    <Dialog open onOpenChange={o => { if (!o) onClose() }}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{t('editName.title')}</DialogTitle>
          <DialogDescription>{t('editName.description')}</DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-3">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="edit-full-name">{t('editName.label')}</Label>
            <Input
              id="edit-full-name"
              autoFocus
              maxLength={MAX_FULL_NAME_LEN}
              value={value}
              onChange={e => { setTouched(true); setValue(e.target.value) }}
              onKeyDown={e => { if (e.key === 'Enter') submit() }}
            />
          </div>

          {touched && error && (
            <p className="text-xs text-red" role="alert">
              {t(`editName.error.${error}`, { max: MAX_FULL_NAME_LEN })}
            </p>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={isPending}>
            {t('common.cancel')}
          </Button>
          <Button onClick={submit} disabled={disabled}>
            {isPending ? t('editName.saving') : t('common.save')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
