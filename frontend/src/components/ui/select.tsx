import * as React from "react"
import { cn } from "@/lib/utils"

const Select = React.forwardRef<
  HTMLSelectElement,
  React.ComponentProps<"select">
>(({ className, children, ...props }, ref) => {
  return (
    <select
      className={cn(
        // appearance:base-select → на Chrome/Edge список опций рисует сам браузер
        // по нашему CSS (компактно, 14px), вместо крупного нативного OS-попапа
        // macOS. Стили самого списка — в index.css (::picker(select)/option).
        // Браузеры без base-select игнорируют значение → нативный список (как было).
        "flex h-9 w-full [appearance:base-select] rounded-sm border border-border-default bg-bg-surface px-3 py-1 text-sm text-text-primary focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent disabled:cursor-not-allowed disabled:opacity-50",
        className
      )}
      ref={ref}
      {...props}
    >
      {children}
    </select>
  )
})

Select.displayName = "Select"

export { Select }
