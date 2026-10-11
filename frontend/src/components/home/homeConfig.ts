import type { BoardConfigData, HomeBlockCfg, HomeBlockId, LocalizedText } from '../../types/boardConfig'
import { HOME_BLOCK_IDS } from '../../types/boardConfig'
import { isElevatorsEnabled, isWorkReportsEnabled } from '../../utils/featureFlags'
import type { Lang } from './homeFormat'

// Эффективные настройки страницы жителей из конфига витрины. Чистые функции:
// страница и превью редактора читают одно и то же.

export interface HomeBlockState {
  visible: boolean
  // Заголовок, заданный менеджером (уже локализованный); '' → i18n-дефолт.
  title: string
}

export type HomeBlocks = Record<HomeBlockId, HomeBlockState>

/** Модуль блока включён в сборке фронта (бэкенд гейтует тем же флагом). */
export function blockModuleEnabled(id: HomeBlockId): boolean {
  if (id === 'elevators') return isElevatorsEnabled()
  if (id === 'workreports') return isWorkReportsEnabled()
  return true
}

export function localize(text: LocalizedText | undefined, lang: Lang): string {
  return ((text?.[lang] || text?.ru) ?? '').trim()
}

/**
 * Видимость и заголовки блоков. Без `home` в конфиге (бэкенд до появления поля)
 * все блоки видимы. Блок, которого нет в `home.blocks`, бэкенд вырезал флагом —
 * он скрыт; так же скрыт блок выключенного на фронте модуля.
 */
export function resolveHomeBlocks(config: BoardConfigData, lang: Lang): HomeBlocks {
  const configured = config.home?.blocks
  const byId = new Map<string, HomeBlockCfg>((configured ?? []).map((b) => [b.id, b]))
  return Object.fromEntries(
    HOME_BLOCK_IDS.map((id) => {
      const block = byId.get(id)
      const present = configured === undefined || block !== undefined
      return [id, {
        visible: present && (block?.visible ?? true) && blockModuleEnabled(id),
        title: localize(block?.title, lang),
      }]
    }),
  ) as HomeBlocks
}

/** Ряды страницы: пары блоков; ряд без видимых блоков пропускается. */
export const HOME_ROWS: readonly (readonly [HomeBlockId, HomeBlockId])[] = [
  ['announcements', 'contacts'],
  ['requests', 'works'],
  ['elevators', 'workreports'],
] as const
