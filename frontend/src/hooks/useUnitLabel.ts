import { useTranslation } from 'react-i18next'
import type { MaterialUnit } from '../types/materials'

/** Локализованная подпись канон-единицы измерения ('m' → 'м'). */
export function useUnitLabel() {
  const { t } = useTranslation()
  return (unit: MaterialUnit | string) => t(`materials.units.${unit}`)
}
