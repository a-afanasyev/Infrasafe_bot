import { describe, expect, it } from 'vitest';
import { testI18n } from '../../../test/test-utils';
import { formatDate, formatMonth, formatNumber, toIntlLocale } from './format';

describe('formatNumber', () => {
  it('обрезает хвостовые нули дробной части', () => {
    expect(formatNumber('123.4500')).toBe('123.45');
    expect(formatNumber('0.5000')).toBe('0.5');
  });

  it('целая часть с нулевой дробью остаётся целой', () => {
    expect(formatNumber('123.0000')).toBe('123');
    expect(formatNumber('0.0000')).toBe('0');
  });

  it('не трогает числа без дробной части', () => {
    expect(formatNumber('1005')).toBe('1005');
    expect(formatNumber(42)).toBe('42');
  });

  it('null/undefined/пустая строка → тире', () => {
    expect(formatNumber(null)).toBe('—');
    expect(formatNumber(undefined)).toBe('—');
    expect(formatNumber('')).toBe('—');
  });

  it('отрицательные значения', () => {
    expect(formatNumber('-12.300')).toBe('-12.3');
  });

  it('нечисловые строки возвращает как есть', () => {
    expect(formatNumber('abc')).toBe('abc');
  });
});

describe('formatMonth', () => {
  it('YYYY-MM → название месяца', () => {
    expect(formatMonth('2026-07', testI18n.t)).toBe('Июль 2026');
  });

  it('название месяца берётся из локали (uz)', () => {
    const uzT = testI18n.getFixedT('uz');
    expect(formatMonth('2026-07', uzT)).toBe('Iyul 2026');
  });

  it('невалидный месяц возвращается как есть', () => {
    expect(formatMonth('2026-13', testI18n.t)).toBe('2026-13');
    expect(formatMonth('garbage', testI18n.t)).toBe('garbage');
  });
});

describe('toIntlLocale / formatDate', () => {
  it('uz → узбекская латиница, остальное → ru-RU', () => {
    expect(toIntlLocale('uz')).toBe('uz-Latn-UZ');
    expect(toIntlLocale('ru')).toBe('ru-RU');
    expect(toIntlLocale(undefined)).toBe('ru-RU');
  });

  it('пустая дата → тире', () => {
    expect(formatDate(null, 'uz-Latn-UZ')).toBe('—');
  });
});
