import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { formatDate, formatDateTime, formatMonth, toIntlLocale } from './format';

/** Форматтеры дат/месяцев, привязанные к текущему языку i18next хоста. */
export function useResourceFormat() {
  const { t, i18n } = useTranslation();
  const locale = toIntlLocale(i18n.language);
  return useMemo(
    () => ({
      formatMonth: (month: string) => formatMonth(month, t),
      formatDateTime: (iso: string | null | undefined) => formatDateTime(iso, locale),
      formatDate: (iso: string | null | undefined) => formatDate(iso, locale),
    }),
    [t, locale],
  );
}
