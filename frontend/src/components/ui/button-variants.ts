import { cva } from "class-variance-authority"

// Вынесено из button.tsx, чтобы файл-компонент экспортировал только компонент
// (react-refresh/only-export-components).
export const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-sm text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        default: "bg-accent text-white hover:bg-accent/90",
        secondary: "bg-bg-surface text-text-primary hover:bg-bg-card-hover",
        destructive: "bg-red text-white hover:bg-red/90",
        ghost: "hover:bg-bg-surface text-text-primary",
        outline:
          "border border-border-default bg-transparent hover:bg-bg-surface text-text-primary",
        link: "text-accent underline-offset-4 hover:underline",
      },
      size: {
        default: "h-9 px-4 py-2",
        sm: "h-8 px-3 text-xs",
        lg: "h-10 px-6",
        icon: "h-9 w-9",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)
