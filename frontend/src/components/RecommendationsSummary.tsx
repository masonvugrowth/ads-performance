'use client'

import Link from 'next/link'
import { useEffect, useState } from 'react'
import InfoTag from '@/components/InfoTag'

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000'

interface Recommendation {
  id: string
  rec_type: string
  severity: 'critical' | 'warning' | 'info'
  title: string
  campaign_id: string | null
  campaign_type: string | null
}

const DOT: Record<string, string> = {
  critical: 'bg-red-500',
  warning: 'bg-amber-500',
  info: 'bg-blue-500',
}

export default function RecommendationsSummary() {
  const [top, setTop] = useState<Recommendation[]>([])
  const [counts, setCounts] = useState({ critical: 0, warning: 0, info: 0 })
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch(`${API_BASE}/api/google/recommendations?status=pending&limit=50`, {
      credentials: 'include',
    })
      .then(r => r.json())
      .then(res => {
        if (!res.success) return
        const items: Recommendation[] = res.data.items || []
        setTop(items.filter(r => r.severity === 'critical').slice(0, 5))
        const c = { critical: 0, warning: 0, info: 0 }
        items.forEach(r => c[r.severity]++)
        setCounts(c)
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  if (loading) return null
  const total = counts.critical + counts.warning + counts.info
  if (total === 0) return null

  return (
    <div className="bg-white border border-gray-200 rounded-lg p-4 mb-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-4">
          <h2 className="text-sm font-bold text-gray-900">Pending recommendations</h2>
          <div className="flex items-center gap-3 text-xs text-gray-600">
            <span className="flex items-center gap-1">
              <span className={`w-2 h-2 rounded-full ${DOT.critical}`} />
              {counts.critical} critical
            </span>
            <span className="flex items-center gap-1">
              <span className={`w-2 h-2 rounded-full ${DOT.warning}`} />
              {counts.warning} warning
            </span>
            <span className="flex items-center gap-1">
              <span className={`w-2 h-2 rounded-full ${DOT.info}`} />
              {counts.info} info
            </span>
          </div>
        </div>
        <Link
          href="/google/recommendations"
          className="text-xs font-medium text-blue-600 hover:text-blue-700"
        >
          View all →
        </Link>
      </div>
      {top.length > 0 && (
        <ul className="space-y-1">
          {top.map(r => (
            <li key={r.id}>
              <Link
                href="/google/recommendations"
                className="flex items-center gap-2 text-sm text-gray-700 hover:text-gray-900"
              >
                <span className={`w-1.5 h-1.5 rounded-full ${DOT.critical}`} />
                <span className="font-medium">{r.title}</span>
                <InfoTag
                  code={r.rec_type}
                  kind="rec_type"
                  className="text-[10px] font-mono text-gray-400"
                />
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
