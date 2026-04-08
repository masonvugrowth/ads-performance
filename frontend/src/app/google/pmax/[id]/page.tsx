'use client'

import { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import Link from 'next/link'

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000'

interface AssetGroup {
  id: string
  name: string
  status: string
  final_urls: string[]
  assets: Asset[]
}

interface Asset {
  id: string
  asset_type: string
  text_content: string | null
  image_url: string | null
  performance_label: string | null
}

interface CampaignDetail {
  id: string
  name: string
  status: string
  campaign_type: string
  daily_budget: number | null
  ta: string | null
  funnel_stage: string | null
}

interface MetricRow {
  date: string
  spend: number
  impressions: number
  clicks: number
  conversions: number
  revenue: number
  roas: number
}

const PERF_COLORS: Record<string, string> = {
  BEST: 'bg-green-100 text-green-700',
  GOOD: 'bg-blue-100 text-blue-700',
  LOW: 'bg-red-100 text-red-700',
  LEARNING: 'bg-yellow-100 text-yellow-700',
  PENDING: 'bg-gray-100 text-gray-500',
}

export default function PMaxDetail() {
  const { id } = useParams<{ id: string }>()
  const [campaign, setCampaign] = useState<CampaignDetail | null>(null)
  const [assetGroups, setAssetGroups] = useState<AssetGroup[]>([])
  const [metrics, setMetrics] = useState<MetricRow[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([
      fetch(`${API_BASE}/api/google/campaigns/${id}`, { credentials: 'include' }).then(r => r.json()),
      fetch(`${API_BASE}/api/google/asset-groups?campaign_id=${id}`, { credentials: 'include' }).then(r => r.json()),
      fetch(`${API_BASE}/api/google/campaigns/${id}/metrics`, { credentials: 'include' }).then(r => r.json()),
    ]).then(async ([campRes, agRes, metRes]) => {
      if (campRes.success) setCampaign(campRes.data)
      if (metRes.success) setMetrics(metRes.data.metrics)

      // Fetch assets for each asset group
      if (agRes.success) {
        const groups: AssetGroup[] = []
        for (const g of agRes.data.asset_groups) {
          const detailRes = await fetch(`${API_BASE}/api/google/asset-groups/${g.id}`, { credentials: 'include' }).then(r => r.json())
          if (detailRes.success) {
            groups.push(detailRes.data)
          }
        }
        setAssetGroups(groups)
      }
    }).finally(() => setLoading(false))
  }, [id])

  const fmt = (n: number) => n.toLocaleString('en-US', { maximumFractionDigits: 2 })

  if (loading) return <div className="p-8 text-gray-500">Loading campaign detail...</div>
  if (!campaign) return <div className="p-8 text-red-500">Campaign not found</div>

  // Aggregate metrics
  const totalSpend = metrics.reduce((s, m) => s + m.spend, 0)
  const totalRevenue = metrics.reduce((s, m) => s + m.revenue, 0)
  const totalConversions = metrics.reduce((s, m) => s + m.conversions, 0)

  return (
    <div className="p-8 space-y-6">
      <div className="flex items-center gap-3">
        <Link href="/google/pmax" className="text-gray-400 hover:text-gray-600">&larr;</Link>
        <div>
          <h1 className="text-2xl font-bold text-gray-900">{campaign.name}</h1>
          <div className="flex items-center gap-3 mt-1">
            <span className="text-xs bg-blue-50 text-blue-700 px-2 py-0.5 rounded-full font-medium">PERFORMANCE MAX</span>
            <span className={`text-xs font-medium ${campaign.status === 'ACTIVE' ? 'text-green-600' : 'text-gray-400'}`}>
              {campaign.status}
            </span>
            {campaign.daily_budget && <span className="text-xs text-gray-500">${fmt(campaign.daily_budget)}/day</span>}
          </div>
        </div>
      </div>

      {/* KPI Summary */}
      <div className="grid grid-cols-4 gap-4">
        <div className="bg-white rounded-xl border p-4">
          <p className="text-xs text-gray-500">Total Spend</p>
          <p className="text-xl font-bold">${fmt(totalSpend)}</p>
        </div>
        <div className="bg-white rounded-xl border p-4">
          <p className="text-xs text-gray-500">Revenue</p>
          <p className="text-xl font-bold">${fmt(totalRevenue)}</p>
        </div>
        <div className="bg-white rounded-xl border p-4">
          <p className="text-xs text-gray-500">ROAS</p>
          <p className="text-xl font-bold">{totalSpend > 0 ? (totalRevenue / totalSpend).toFixed(2) : '0'}x</p>
        </div>
        <div className="bg-white rounded-xl border p-4">
          <p className="text-xs text-gray-500">Conversions</p>
          <p className="text-xl font-bold">{totalConversions}</p>
        </div>
      </div>

      {/* Asset Groups */}
      <div className="space-y-4">
        <h2 className="text-lg font-semibold text-gray-900">Asset Groups ({assetGroups.length})</h2>

        {assetGroups.map(group => (
          <div key={group.id} className="bg-white rounded-xl border border-gray-200 overflow-hidden">
            <div className="p-5 border-b border-gray-100">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="font-medium text-gray-900">{group.name}</h3>
                  <p className="text-xs text-gray-500 mt-1">{group.assets.length} assets</p>
                </div>
                <span className={`text-xs font-medium ${group.status === 'ACTIVE' ? 'text-green-600' : 'text-gray-400'}`}>
                  {group.status}
                </span>
              </div>
            </div>

            <div className="p-5 space-y-4">
              {/* Headlines */}
              {group.assets.filter(a => a.asset_type === 'HEADLINE').length > 0 && (
                <div>
                  <p className="text-xs font-semibold text-gray-500 uppercase mb-2">Headlines</p>
                  <div className="space-y-1">
                    {group.assets.filter(a => a.asset_type === 'HEADLINE').map(a => (
                      <div key={a.id} className="flex items-center justify-between py-1">
                        <span className="text-sm text-gray-700">{a.text_content}</span>
                        {a.performance_label && (
                          <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${PERF_COLORS[a.performance_label] || 'bg-gray-100 text-gray-500'}`}>
                            {a.performance_label}
                          </span>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Descriptions */}
              {group.assets.filter(a => a.asset_type === 'DESCRIPTION').length > 0 && (
                <div>
                  <p className="text-xs font-semibold text-gray-500 uppercase mb-2">Descriptions</p>
                  <div className="space-y-1">
                    {group.assets.filter(a => a.asset_type === 'DESCRIPTION').map(a => (
                      <div key={a.id} className="flex items-center justify-between py-1">
                        <span className="text-sm text-gray-700">{a.text_content}</span>
                        {a.performance_label && (
                          <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${PERF_COLORS[a.performance_label] || 'bg-gray-100 text-gray-500'}`}>
                            {a.performance_label}
                          </span>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Images */}
              {group.assets.filter(a => a.asset_type === 'IMAGE' || a.asset_type === 'LOGO').length > 0 && (
                <div>
                  <p className="text-xs font-semibold text-gray-500 uppercase mb-2">Images</p>
                  <div className="grid grid-cols-4 gap-3">
                    {group.assets.filter(a => a.asset_type === 'IMAGE' || a.asset_type === 'LOGO').map(a => (
                      <div key={a.id} className="relative">
                        {a.image_url ? (
                          <img
                            src={a.image_url}
                            alt={a.asset_type}
                            className="w-full h-24 object-cover rounded-lg border"
                          />
                        ) : (
                          <div className="w-full h-24 bg-gray-100 rounded-lg flex items-center justify-center text-xs text-gray-400">
                            {a.asset_type}
                          </div>
                        )}
                        {a.performance_label && (
                          <span className={`absolute top-1 right-1 text-[9px] px-1 py-0.5 rounded ${PERF_COLORS[a.performance_label] || ''}`}>
                            {a.performance_label}
                          </span>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Videos */}
              {group.assets.filter(a => a.asset_type === 'VIDEO').length > 0 && (
                <div>
                  <p className="text-xs font-semibold text-gray-500 uppercase mb-2">Videos</p>
                  <div className="space-y-1">
                    {group.assets.filter(a => a.asset_type === 'VIDEO').map(a => (
                      <a key={a.id} href={a.image_url || '#'} target="_blank" rel="noopener noreferrer"
                        className="text-sm text-blue-600 hover:underline block py-1">
                        {a.image_url || 'Video asset'}
                      </a>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* Daily Metrics */}
      {metrics.length > 0 && (
        <div className="bg-white rounded-xl border border-gray-200">
          <div className="p-5 border-b border-gray-100">
            <h2 className="font-semibold text-gray-900">Daily Metrics</h2>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50">
                <tr>
                  <th className="text-left px-5 py-3 text-gray-500 font-medium">Date</th>
                  <th className="text-right px-5 py-3 text-gray-500 font-medium">Spend</th>
                  <th className="text-right px-5 py-3 text-gray-500 font-medium">Impressions</th>
                  <th className="text-right px-5 py-3 text-gray-500 font-medium">Clicks</th>
                  <th className="text-right px-5 py-3 text-gray-500 font-medium">Conv.</th>
                  <th className="text-right px-5 py-3 text-gray-500 font-medium">Revenue</th>
                  <th className="text-right px-5 py-3 text-gray-500 font-medium">ROAS</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {metrics.map(m => (
                  <tr key={m.date} className="hover:bg-gray-50">
                    <td className="px-5 py-3 text-gray-700">{m.date}</td>
                    <td className="px-5 py-3 text-right">${fmt(m.spend)}</td>
                    <td className="px-5 py-3 text-right">{fmt(m.impressions)}</td>
                    <td className="px-5 py-3 text-right">{fmt(m.clicks)}</td>
                    <td className="px-5 py-3 text-right">{m.conversions}</td>
                    <td className="px-5 py-3 text-right">${fmt(m.revenue)}</td>
                    <td className="px-5 py-3 text-right font-medium">{m.roas.toFixed(2)}x</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
