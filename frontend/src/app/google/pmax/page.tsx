'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000'

interface AssetGroup {
  id: string
  campaign_id: string
  campaign_name: string | null
  name: string
  status: string
  final_urls: string[]
  asset_count: number
}

interface Campaign {
  id: string
  name: string
  status: string
  daily_budget: number | null
  ta: string | null
  funnel_stage: string | null
}

export default function PMaxPage() {
  const [campaigns, setCampaigns] = useState<Campaign[]>([])
  const [assetGroups, setAssetGroups] = useState<AssetGroup[]>([])
  const [loading, setLoading] = useState(true)
  const [expandedCampaign, setExpandedCampaign] = useState<string | null>(null)

  useEffect(() => {
    Promise.all([
      fetch(`${API_BASE}/api/google/campaigns?campaign_type=PERFORMANCE_MAX&limit=100`, { credentials: 'include' }).then(r => r.json()),
      fetch(`${API_BASE}/api/google/asset-groups?limit=200`, { credentials: 'include' }).then(r => r.json()),
    ]).then(([campRes, agRes]) => {
      if (campRes.success) setCampaigns(campRes.data.campaigns)
      if (agRes.success) setAssetGroups(agRes.data.asset_groups)
    }).finally(() => setLoading(false))
  }, [])

  const fmtCurrency = (n: number) => `$${n.toLocaleString('en-US', { maximumFractionDigits: 2 })}`

  if (loading) return <div className="p-8 text-gray-500">Loading PMax campaigns...</div>

  return (
    <div className="p-8 space-y-6">
      <div className="flex items-center gap-3">
        <Link href="/google" className="text-gray-400 hover:text-gray-600">&larr;</Link>
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Performance Max Campaigns</h1>
          <p className="text-sm text-gray-500">{campaigns.length} campaigns, {assetGroups.length} asset groups</p>
        </div>
      </div>

      {campaigns.length === 0 ? (
        <div className="bg-white rounded-xl border border-gray-200 p-10 text-center text-gray-400">
          No PMax campaigns found. Sync Google Ads data first.
        </div>
      ) : (
        <div className="space-y-3">
          {campaigns.map((c) => {
            const groups = assetGroups.filter(ag => ag.campaign_id === c.id)
            const isExpanded = expandedCampaign === c.id

            return (
              <div key={c.id} className="bg-white rounded-xl border border-gray-200 overflow-hidden">
                <button
                  onClick={() => setExpandedCampaign(isExpanded ? null : c.id)}
                  className="w-full flex items-center justify-between p-5 hover:bg-gray-50 transition-colors text-left"
                >
                  <div className="flex items-center gap-4">
                    <div className="w-10 h-10 bg-blue-50 rounded-lg flex items-center justify-center text-blue-600 font-bold text-sm">
                      PM
                    </div>
                    <div>
                      <Link href={`/google/pmax/${c.id}`} className="font-medium text-gray-900 hover:text-blue-600">
                        {c.name}
                      </Link>
                      <div className="flex items-center gap-3 mt-1">
                        <span className={`text-xs ${c.status === 'ACTIVE' ? 'text-green-600' : 'text-gray-400'}`}>
                          {c.status}
                        </span>
                        {c.daily_budget && <span className="text-xs text-gray-500">{fmtCurrency(c.daily_budget)}/day</span>}
                        {c.ta && <span className="text-xs bg-gray-100 px-1.5 py-0.5 rounded">{c.ta}</span>}
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="text-sm text-gray-500">{groups.length} asset groups</span>
                    <span className="text-gray-400">{isExpanded ? '▲' : '▼'}</span>
                  </div>
                </button>

                {isExpanded && groups.length > 0 && (
                  <div className="border-t border-gray-100 divide-y divide-gray-50">
                    {groups.map(g => (
                      <Link
                        key={g.id}
                        href={`/google/pmax/${c.id}?group=${g.id}`}
                        className="flex items-center justify-between px-5 py-3 pl-16 hover:bg-blue-50 transition-colors"
                      >
                        <div>
                          <p className="text-sm font-medium text-gray-700">{g.name}</p>
                          <p className="text-xs text-gray-400">{g.asset_count} assets</p>
                        </div>
                        <span className={`text-xs ${g.status === 'ACTIVE' ? 'text-green-600' : 'text-gray-400'}`}>
                          {g.status}
                        </span>
                      </Link>
                    ))}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
