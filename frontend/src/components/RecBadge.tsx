'use client'

import Link from 'next/link'
import { useEffect, useState } from 'react'

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000'

interface Counts {
  critical: number
  warning: number
  info: number
}

export default function RecBadge({
  campaignId,
  className = '',
}: {
  campaignId: string | null | undefined
  className?: string
}) {
  const [counts, setCounts] = useState<Counts | null>(null)

  useEffect(() => {
    if (!campaignId) return
    let cancelled = false
    fetch(
      `${API_BASE}/api/google/recommendations-counts/campaign/${campaignId}`,
      { credentials: 'include' },
    )
      .then(r => r.json())
      .then(res => {
        if (cancelled) return
        if (res.success) setCounts(res.data)
      })
      .catch(() => {})
    return () => { cancelled = true }
  }, [campaignId])

  if (!campaignId || !counts) return null
  const total = counts.critical + counts.warning + counts.info
  if (total === 0) {
    return (
      <Link
        href={`/google/recommendations?campaign_id=${campaignId}`}
        className={`inline-flex items-center gap-1 px-2 py-1 rounded-md text-xs font-medium bg-gray-50 text-gray-500 border border-gray-200 hover:bg-gray-100 ${className}`}
      >
        No pending recs
      </Link>
    )
  }
  return (
    <Link
      href={`/google/recommendations?campaign_id=${campaignId}`}
      className={`inline-flex items-center gap-2 px-2.5 py-1 rounded-md text-xs font-medium border ${
        counts.critical > 0
          ? 'bg-red-50 text-red-700 border-red-200'
          : counts.warning > 0
          ? 'bg-amber-50 text-amber-800 border-amber-200'
          : 'bg-blue-50 text-blue-700 border-blue-200'
      } ${className}`}
      title="Open recommendations for this campaign"
    >
      <span className="font-bold">{total}</span>
      <span>recommendation{total === 1 ? '' : 's'}</span>
      {counts.critical > 0 && (
        <span className="px-1.5 py-0.5 rounded bg-red-600 text-white font-bold">
          {counts.critical} critical
        </span>
      )}
    </Link>
  )
}
