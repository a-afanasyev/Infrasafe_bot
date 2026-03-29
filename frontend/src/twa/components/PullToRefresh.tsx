import { useState, useRef, useCallback } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useTelegramSDK } from '../hooks/useTelegramSDK'

interface Props {
  queryKeys: string[][]
  children: React.ReactNode
}

export default function PullToRefresh({ queryKeys, children }: Props) {
  const queryClient = useQueryClient()
  const { haptic } = useTelegramSDK()
  const [pulling, setPulling] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const startY = useRef(0)
  const pullDistance = useRef(0)
  const containerRef = useRef<HTMLDivElement>(null)

  const onTouchStart = useCallback((e: React.TouchEvent) => {
    if (containerRef.current && containerRef.current.scrollTop === 0) {
      startY.current = e.touches[0].clientY
    }
  }, [])

  const onTouchMove = useCallback((e: React.TouchEvent) => {
    if (!startY.current) return
    const diff = e.touches[0].clientY - startY.current
    if (diff > 0 && diff < 120) {
      pullDistance.current = diff
      setPulling(diff > 50)
    }
  }, [])

  const onTouchEnd = useCallback(async () => {
    if (pullDistance.current > 50 && !refreshing) {
      setRefreshing(true)
      haptic('impact')
      await Promise.all(
        queryKeys.map(key => queryClient.invalidateQueries({ queryKey: key }))
      )
      setRefreshing(false)
    }
    startY.current = 0
    pullDistance.current = 0
    setPulling(false)
  }, [queryKeys, queryClient, haptic, refreshing])

  return (
    <div
      ref={containerRef}
      onTouchStart={onTouchStart}
      onTouchMove={onTouchMove}
      onTouchEnd={onTouchEnd}
      className="relative"
    >
      {(pulling || refreshing) && (
        <div className="flex justify-center py-2 text-emerald-500 text-[12px]">
          {refreshing ? '↻ ...' : '↓ pull'}
        </div>
      )}
      {children}
    </div>
  )
}
