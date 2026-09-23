/**
 * Показания приходят строками с фиксированной точностью (например "123.4500").
 * Для отображения обрезаем хвостовые нули дробной части, "123.0000" -> "123".
 */
export function formatNumber(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === '') return '—';
  const s = String(value);
  if (!/^-?\d+(\.\d+)?$/.test(s)) return s;
  if (!s.includes('.')) return s;
  const trimmed = s.replace(/0+$/, '').replace(/\.$/, '');
  return trimmed === '' || trimmed === '-' ? '0' : trimmed;
}

/** Минимальная сигнатура t — модуль не тянет типы хоста. */
type Translate = (key: string) => string;

const MONTH_KEYS = [
  'resourceAccounting.months.m01', 'resourceAccounting.months.m02', 'resourceAccounting.months.m03',
  'resourceAccounting.months.m04', 'resourceAccounting.months.m05', 'resourceAccounting.months.m06',
  'resourceAccounting.months.m07', 'resourceAccounting.months.m08', 'resourceAccounting.months.m09',
  'resourceAccounting.months.m10', 'resourceAccounting.months.m11', 'resourceAccounting.months.m12',
] as const;

/** i18next-язык хоста → Intl-локаль ('uz' → узбекская латиница, иначе русская). */
export function toIntlLocale(lang: string | undefined): string {
  return lang?.startsWith('uz') ? 'uz-Latn-UZ' : 'ru-RU';
}

/** 'YYYY-MM' → «Июль 2026» / «Iyul 2026» (название месяца — из локали хоста). */
export function formatMonth(month: string, t: Translate): string {
  const [year, m] = month.split('-');
  const idx = Number(m) - 1;
  if (!year || !(idx >= 0 && idx <= 11)) return month;
  return `${t(MONTH_KEYS[idx])} ${year}`;
}

export function formatDateTime(iso: string | null | undefined, locale = 'ru-RU'): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(locale, {
    day: '2-digit', month: '2-digit', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  });
}

export function formatDate(iso: string | null | undefined, locale = 'ru-RU'): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(locale);
}
