import { createContext, useContext } from 'react';

/**
 * Базовый путь монтирования модуля в хосте (напр. '/dashboard/resource-accounting').
 * В standalone — '' (роуты в корне). Ссылки/навигация строятся через useResourceLink,
 * чтобы модуль работал под любым префиксом хоста без правок страниц.
 */
export const ResourceBasePathContext = createContext<string>('');

export function useResourceBasePath(): string {
  return useContext(ResourceBasePathContext);
}

/** Возвращает функцию-построитель ссылок: link('/meters/123') → base + путь. */
export function useResourceLink(): (path: string) => string {
  const base = useResourceBasePath();
  return (path: string) => `${base}${path}`;
}
