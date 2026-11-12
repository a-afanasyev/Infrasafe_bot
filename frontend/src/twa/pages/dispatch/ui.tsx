import type { ReactNode } from 'react'

export function Title({ children }: { children: ReactNode }) {
  return <h1 className="text-[24px] font-bold text-gray-900 dark:text-gray-50">{children}</h1>
}

export function Hint({ children }: { children: ReactNode }) {
  return <p className="text-[18px] text-gray-600 dark:text-gray-300">{children}</p>
}
