export default function LoadingSpinner() {
  return (
    <div className="flex items-center justify-center p-12">
      <div className="h-9 w-9 rounded-full border-3 border-border-default border-t-accent animate-spin" />
    </div>
  )
}
