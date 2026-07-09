// Brand variant, selected at build time via VITE_BRAND (см. Dockerfile /
// docker-compose.profk.yml). Vite инлайнит import.meta.env.VITE_BRAND в бандл,
// поэтому переключение бренда — нулевой рантайм-оверхед. Дефолт — infrasafe.

export type BrandId = 'infrasafe' | 'profk'

export const BRAND: BrandId =
  import.meta.env.VITE_BRAND === 'profk' ? 'profk' : 'infrasafe'

interface BrandConfig {
  id: BrandId
  displayName: string
  productTitle: string
  // Квадратный лого-знак для слотов 52/40px (сайдбар, логин, регистрация).
  logoMark: string
  // Горизонтальный вордмарк — задел (напр. футер); сейчас не рендерится.
  logoFull: string
  // Короткий бейдж для публичного табло (ResidentBoardPage).
  boardBadge: string
  // В брендбуке PROFK нет тёмной темы → тема принудительно светлая,
  // переключатель скрыт.
  lightOnly: boolean
}

const CONFIGS: Record<BrandId, BrandConfig> = {
  infrasafe: {
    id: 'infrasafe',
    displayName: 'InfraSafe',
    productTitle: 'UK Management',
    logoMark: 'infrasafe-logo.svg',
    logoFull: 'infrasafe-logo.svg',
    boardBadge: 'УК',
    lightOnly: false,
  },
  profk: {
    id: 'profk',
    displayName: 'PROFK',
    productTitle: 'PROFK',
    logoMark: 'profk-mark.svg',
    logoFull: 'profk-logo.svg',
    boardBadge: 'PF',
    lightOnly: true,
  },
}

export const brand = CONFIGS[BRAND]
