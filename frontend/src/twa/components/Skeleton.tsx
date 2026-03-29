/**
 * Skeleton loading placeholder for TWA lists.
 */
export function CardSkeleton({ count = 3 }: { count?: number }) {
  return (
    <div className="space-y-2">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="bg-white dark:bg-gray-800 rounded-2xl p-3.5 border border-gray-100 dark:border-gray-700 animate-pulse">
          <div className="flex justify-between mb-2">
            <div className="h-3 bg-gray-200 dark:bg-gray-700 rounded w-20" />
            <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded-full w-16" />
          </div>
          <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-32 mb-1" />
          <div className="h-3 bg-gray-200 dark:bg-gray-700 rounded w-full" />
        </div>
      ))}
    </div>
  )
}

export function ShiftSkeleton() {
  return (
    <div className="bg-white dark:bg-gray-800 rounded-2xl p-6 border border-gray-100 dark:border-gray-700 animate-pulse text-center">
      <div className="w-16 h-16 rounded-full bg-gray-200 dark:bg-gray-700 mx-auto mb-3" />
      <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-32 mx-auto mb-2" />
      <div className="h-8 bg-gray-200 dark:bg-gray-700 rounded w-40 mx-auto mb-4" />
      <div className="h-12 bg-gray-200 dark:bg-gray-700 rounded-xl w-full" />
    </div>
  )
}
