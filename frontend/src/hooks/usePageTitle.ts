import { useEffect } from 'react'

// WR-07: `enabled` lets a component opt out of owning the document title when it
// is rendered as an embedded preview (e.g. ResidentBoardPage inside the board
// editor), so its effect doesn't clobber the host page's title.
export function usePageTitle(title: string, enabled = true) {
  useEffect(() => {
    if (!enabled) return
    document.title = title ? `${title} — UK Management` : 'UK Management'
  }, [title, enabled])
}
