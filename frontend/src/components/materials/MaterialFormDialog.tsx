import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select } from '@/components/ui/select'
import { useCreateMaterial, useUpdateMaterial } from '../../hooks/useMaterials'
import { useUnitLabel } from '../../hooks/useUnitLabel'
import { MATERIAL_UNITS, type MaterialCard, type MaterialUnit } from '../../types/materials'

/**
 * Создание/правка карточки материала. name UNIQUE навсегда (дубль → 409 с
 * подсказкой реактивировать); unit при наличии движений backend не даст сменить.
 */
interface Props {
  open: boolean
  material?: MaterialCard | null // null/undefined = создание
  onClose: () => void
}

export default function MaterialFormDialog({ open, material, onClose }: Props) {
  const { t } = useTranslation()
  const unitLabel = useUnitLabel()
  const createMutation = useCreateMaterial()
  const updateMutation = useUpdateMaterial()

  const [name, setName] = useState('')
  const [unit, setUnit] = useState<MaterialUnit>('pcs')
  const [category, setCategory] = useState('')
  const [minStock, setMinStock] = useState('')
  const [isActive, setIsActive] = useState(true)

  // Render-time reset при открытии (паттерн ZoneFormDialog — без useEffect)
  const [prevOpen, setPrevOpen] = useState(false)
  if (open !== prevOpen) {
    setPrevOpen(open)
    if (open) {
      setName(material?.name ?? '')
      setUnit(material?.unit ?? 'pcs')
      setCategory(material?.category ?? '')
      setMinStock(material?.min_stock ?? '')
      setIsActive(material?.is_active ?? true)
    }
  }

  const loading = createMutation.isPending || updateMutation.isPending
  const canSubmit = name.trim().length > 0 && !loading

  const submit = () => {
    if (material) {
      updateMutation.mutate(
        {
          id: material.id,
          name: name.trim(),
          unit,
          category: category.trim(),
          min_stock: minStock.trim() === '' ? null : minStock.trim(),
          is_active: isActive,
        },
        { onSuccess: onClose },
      )
    } else {
      createMutation.mutate(
        {
          name: name.trim(),
          unit,
          category: category.trim() || undefined,
          min_stock: minStock.trim() || undefined,
        },
        { onSuccess: onClose },
      )
    }
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>
            {material ? t('materials.form.editTitle') : t('materials.form.createTitle')}
          </DialogTitle>
        </DialogHeader>
        <div className="flex flex-col gap-3">
          <div className="flex flex-col gap-1.5">
            <Label>{t('materials.form.name')}</Label>
            <Input value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label>{t('materials.form.unit')}</Label>
            <Select value={unit} onChange={(e) => setUnit(e.target.value as MaterialUnit)}>
              {MATERIAL_UNITS.map((u) => (
                <option key={u} value={u}>{unitLabel(u)}</option>
              ))}
            </Select>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label>{t('materials.form.category')}</Label>
            <Input value={category} onChange={(e) => setCategory(e.target.value)} />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label>{t('materials.form.minStock')}</Label>
            <Input
              type="number"
              min="0"
              step="0.001"
              value={minStock}
              onChange={(e) => setMinStock(e.target.value)}
            />
          </div>
          {material && (
            <label className="flex items-center gap-2 text-sm text-text-primary">
              <input
                type="checkbox"
                checked={isActive}
                onChange={(e) => setIsActive(e.target.checked)}
              />
              {t('materials.form.isActive')}
            </label>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={loading}>
            {t('common.cancel')}
          </Button>
          <Button onClick={submit} disabled={!canSubmit}>
            {loading ? t('common.saving') : t('common.save')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
