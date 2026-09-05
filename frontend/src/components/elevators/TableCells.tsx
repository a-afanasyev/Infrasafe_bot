/** Ячейки таблиц модуля «Лифты» — стиль MaterialsPage. */

export function Th({ children }: { children?: React.ReactNode }) {
  return (
    <th className="px-3 py-2.5 text-left text-[10px] font-bold uppercase tracking-wider text-text-muted font-[family-name:var(--font-display)] whitespace-nowrap">
      {children}
    </th>
  )
}

export function Td({ children, className = '' }: { children?: React.ReactNode; className?: string }) {
  return <td className={`px-3 py-2 text-[13px] text-text-primary ${className}`}>{children}</td>
}

export function TableShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="overflow-x-auto rounded-default border border-border-default bg-bg-card">
      <table className="w-full border-collapse">{children}</table>
    </div>
  )
}

export function HeadRow({ children }: { children: React.ReactNode }) {
  return <tr className="bg-bg-surface border-b border-border-default">{children}</tr>
}

export function BodyRow({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  return <tr className={`border-b border-border-default last:border-0 ${className}`}>{children}</tr>
}
