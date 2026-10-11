// Конфиг публичной витрины resident-board. Зеркало backend-схемы
// uk_management_bot/api/board_config/schemas.py.

export interface LocalizedText {
  ru: string
  uz: string
}

export interface OrgCfg {
  name: LocalizedText
  subtitle: LocalizedText
}

export interface ContactsCfg {
  dispatch_phone: string
  dispatch_label: LocalizedText
  emergency: LocalizedText
}

export interface BotCfg {
  username: string
  label: LocalizedText
}

export interface AnnouncementCfg {
  id: string
  icon: string
  important: boolean
  title: LocalizedText
  text: LocalizedText
  published_at: string
}

export interface WorkingHourCfg {
  day: string
  open: string
  close: string
  closed: boolean
}

export type ModuleId =
  | 'stats'
  | 'requests'
  | 'announcements'
  | 'rating'
  | 'hours'
  | 'workreports'
  | 'elevators'

export const MODULE_IDS: ModuleId[] = [
  'stats',
  'requests',
  'announcements',
  'rating',
  'hours',
  'workreports',
  'elevators',
]

export type ModuleWidth = 'full' | 'half'

export interface LayoutItem {
  id: ModuleId
  visible: boolean
  // Ширина блока на табло. Два соседних видимых 'half' встают в один ряд.
  // Отсутствие поля трактуется как 'full' (обратная совместимость).
  width?: ModuleWidth
}

// Настройки будущего модуля отчётов о выполненных работах (НЕ layout-запись —
// та лежит в LayoutItem с id='workreports').
export interface WorkReportsCfg {
  autopost: boolean
  autopost_since: string | null // ISO datetime string over the wire, or null
  // Публикация БЕЗ модерации: черновик с обеими сторонами фото уезжает в ленту
  // сразу. Адрес анонимизируется кодом, содержимое снимка — нет, поэтому
  // единственный контроль за ним в этом режиме отсутствует.
  autopublish: boolean
  // Фильтр «какие категории попадают в ленту». ПУСТОЙ = без ограничения.
  categories: string[]
  limit: number
  title: LocalizedText
}

// Настройки модуля «Лифты» на табло (T16): только заголовок, лимитов нет.
// Пустой заголовок = i18n-дефолт на клиенте.
export interface ElevatorsCfg {
  title: LocalizedText
}

// Плановая работа для блока «Ближайшие работы» страницы жителей.
// date — бизнес-дата YYYY-MM-DD; время HH:MM или '' («в течение дня»).
export interface PlannedWorkCfg {
  id: string
  date: string
  time_from: string
  time_to: string
  title: LocalizedText
  place: LocalizedText
  text: LocalizedText
}

// Страница жителей (/home): блоки в каноническом порядке — сетка свёрстана,
// менеджер включает/выключает блоки и меняет заголовки, но не переставляет.
// Зеркало HOME_BLOCK_IDS бэкенда (services/board_config/defaults.py).
export const HOME_BLOCK_IDS = ['announcements', 'contacts', 'requests', 'works', 'elevators', 'workreports'] as const
export type HomeBlockId = (typeof HOME_BLOCK_IDS)[number]

export interface HomeBlockCfg {
  id: HomeBlockId
  visible: boolean
  // Пусто = i18n-дефолт.
  title: LocalizedText
}

// Пустые тексты = i18n-дефолт на клиенте.
export interface HomeCfg {
  complex_name: LocalizedText
  title: LocalizedText
  eyebrow: LocalizedText
  tagline: LocalizedText
  blocks: HomeBlockCfg[]
}

const EMPTY_TEXT: LocalizedText = { ru: '', uz: '' }

export const defaultHomeConfig: HomeCfg = {
  complex_name: EMPTY_TEXT,
  title: EMPTY_TEXT,
  eyebrow: EMPTY_TEXT,
  tagline: EMPTY_TEXT,
  blocks: HOME_BLOCK_IDS.map((id) => ({ id, visible: true, title: EMPTY_TEXT })),
}

export interface BoardConfigData {
  org: OrgCfg
  contacts: ContactsCfg
  bot: BotCfg
  announcements: AnnouncementCfg[]
  working_hours: WorkingHourCfg[]
  layout: LayoutItem[]
  work_reports: WorkReportsCfg
  // Опционально: ответ бэкенда до T16 (rolling deploy) блока не несёт.
  elevators?: ElevatorsCfg
  // Опционально по той же причине: ответ бэкенда до появления поля.
  planned_works?: PlannedWorkCfg[]
  // Опционально: ответ бэкенда до появления поля. Блоки «Лифты»/«Отчёты»
  // бэкенд вырезает из ответа, пока их модуль выключен флагом.
  home?: HomeCfg
}

// ARCH-137 B5: ответ публичного board-config несёт display_tz — зону показа
// развёртывания. Поле принадлежит ТОЛЬКО ответу: PUT-схема бэка строгая
// (extra="forbid"), echo поля при сохранении витрины = 422.
export interface BoardConfigResponse extends BoardConfigData {
  display_tz: string
}

// Ответ → редактируемый конфиг: снимает display_tz (и глубоко копирует).
// Единственный легальный путь посева draft'а редактора из ответа сервера.
export function toEditableBoardConfig(c: BoardConfigResponse | BoardConfigData): BoardConfigData {
  const editable = JSON.parse(JSON.stringify(c)) as BoardConfigData & { display_tz?: string }
  delete editable.display_tz
  return editable
}

// Fallback, если конфиг ещё не загрузился — страница не должна белеть.
export const defaultBoardConfig: BoardConfigData = {
  org: {
    name: { ru: 'Управляющая компания', uz: 'Boshqaruv kompaniyasi' },
    subtitle: {
      ru: 'ЖК Olmazor Business City · Информационное табло для жителей',
      uz: 'TJM Olmazor Business City · Aholilar uchun axborot tablosi',
    },
  },
  contacts: {
    dispatch_phone: '+998 71 123-45-67',
    dispatch_label: { ru: 'Диспетчерская', uz: 'Dispetcherlik' },
    emergency: {
      ru: 'Аварийная служба: круглосуточно',
      uz: 'Favqulodda xizmat: kunduzi-kechasi',
    },
  },
  bot: {
    username: 'uk_management_bot',
    label: { ru: 'Telegram-бот', uz: 'Telegram-bot' },
  },
  announcements: [
    {
      id: 'default-planned-works',
      icon: '⚠️',
      important: true,
      title: { ru: 'Плановые работы', uz: 'Rejalashtirilgan ishlar' },
      text: {
        ru: 'промывка отопительной системы — 13 марта, 10:00–14:00',
        uz: 'isitish tizimini yuvish — 13 mart, 10:00–14:00',
      },
      published_at: '2026-03-10T09:00:00',
    },
    {
      id: 'default-announcement',
      icon: '📢',
      important: false,
      title: { ru: 'Объявления', uz: "E'lonlar" },
      text: { ru: '', uz: '' },
      published_at: '2026-03-09T14:30:00',
    },
  ],
  working_hours: [
    { day: 'mon', open: '08:00', close: '20:00', closed: false },
    { day: 'tue', open: '08:00', close: '20:00', closed: false },
    { day: 'wed', open: '08:00', close: '20:00', closed: false },
    { day: 'thu', open: '08:00', close: '20:00', closed: false },
    { day: 'fri', open: '08:00', close: '20:00', closed: false },
    { day: 'sat', open: '09:00', close: '17:00', closed: false },
    { day: 'sun', open: '10:00', close: '16:00', closed: false },
  ],
  layout: [
    { id: 'stats', visible: true, width: 'full' },
    { id: 'requests', visible: true, width: 'full' },
    { id: 'announcements', visible: true, width: 'full' },
    { id: 'rating', visible: true, width: 'half' },
    { id: 'hours', visible: true, width: 'half' },
  ],
  work_reports: {
    autopost: false,
    autopost_since: null,
    autopublish: false,
    categories: [],
    limit: 6,
    title: { ru: 'Отчёты о выполненных работах', uz: 'Bajarilgan ishlar hisobotlari' },
  },
  elevators: {
    title: { ru: 'Лифты', uz: 'Liftlar' },
  },
  planned_works: [],
  home: defaultHomeConfig,
}
