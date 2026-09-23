import { useLocation } from 'react-router'
import { Toaster } from '../ui/sonner'

// Mini App (/twa/*) монтирует свой Toaster (top-center, closeButton) и
// рендерится внутри корневого App — без этой проверки каждый тост в TWA
// показывался дважды.
export default function RootToaster() {
  const { pathname } = useLocation()
  if (pathname === '/twa' || pathname.startsWith('/twa/')) return null
  return <Toaster position="bottom-right" richColors />
}
