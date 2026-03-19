import { Toaster as Sonner, type ToasterProps } from "sonner"
import { cn } from "@/lib/utils"

function Toaster({ ...props }: ToasterProps) {
  return (
    <Sonner
      className="toaster group"
      toastOptions={{
        classNames: {
          toast: cn(
            "group toast group-[.toaster]:bg-bg-card group-[.toaster]:text-text-primary group-[.toaster]:border-border-default group-[.toaster]:shadow-lg group-[.toaster]:rounded-default"
          ),
          description: "group-[.toast]:text-text-muted",
          actionButton: "group-[.toast]:bg-accent group-[.toast]:text-white",
          cancelButton: "group-[.toast]:bg-bg-surface group-[.toast]:text-text-muted",
          success:
            "group-[.toast]:!bg-[var(--emerald)]/10 group-[.toast]:!border-[var(--emerald)]/30 group-[.toast]:!text-emerald",
          error:
            "group-[.toast]:!bg-[var(--red)]/10 group-[.toast]:!border-[var(--red)]/30 group-[.toast]:!text-red",
          warning:
            "group-[.toast]:!bg-[var(--amber)]/10 group-[.toast]:!border-[var(--amber)]/30 group-[.toast]:!text-amber",
          info:
            "group-[.toast]:!bg-[var(--blue)]/10 group-[.toast]:!border-[var(--blue)]/30 group-[.toast]:!text-blue",
        },
      }}
      {...props}
    />
  )
}

export { Toaster }
