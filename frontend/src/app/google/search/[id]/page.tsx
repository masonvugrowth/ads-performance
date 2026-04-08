'use client'

import { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import Link from 'next/link'

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000'

interface CampaignDetail {
  id: string
  name: string
  status: string
  daily_budget: number | null
  ta: string | null
  funnel_stage: string | null
}

interface AdGroup {
  id: string
  name: string
  status: string
  country: string | null
}

interface GoogleAd {
  id: string
  name: string
  status: string
  ad_type: string
  headlines: string[]
  descriptions: string[]
}

interface MetricRow {
  date: string
  spend: number
  impressions: number
  clicks: number
  conversions: number
  revenue: number
  roas: number
  ctr: number
  cpa: number | null
}

export default function SearchCampaignDetail() {
  const { id } = useParams<{ id: string }>()
  const [campaign, setCampaign] = useState<CampaignDetail | null>(null)
  const [adGroups, setAdGroups] = useState<AdGroup[]>([])
  const [ads, setAds] = useState<Record<string, GoogleAd[]>>({})
  const [metrics, setMetrics] = useState<MetricRow[]>([])
  const [expandedGroup, setExpandedGroup] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([
      fetch(`${API_BASE}/api/google/campaigns/${id}`, { credentials: 'include' }).then(r => r.json()),
      fetch(`${API_BASE}/api/google/campaigns/${id}/ad-groups`, { credentials: 'include' }).then(r => r.json()),
      fetch(`${API_BASE}/api/google/campaigns/${id}/metrics`, { credentials: 'include' }).then(r => r.json()),
    ]).then(([campRes, agRes, metRes]) => {
      if (campRes.success) setCampaign(campRes.data)
      if (agRes.success) setAdGroups(agRes.data.ad_groups)
      if (metRes.success) setMetrics(metRes.data.metrics)
    }).finally(() => setLoading(false))
  }, [id])

  const loadAds = async (adGroupId: string) => {
    if (ads[adGroupId]) {
      setExpandedGroup(expandedGroup === adGroupId ? null : adGroupId)
      return
    }
    // Note: We'd need an endpoint to fetch ads by ad_group. For now, we show ad group info.
    setExpandedGroup(expandedGroup === adGroupId ? null : adGroupId)
  }

  const fmt = (n: number) => n.toLocaleString('en-US', { maximumFractionDigits: 2 })

  if (loading) return <div className="p-8 text-gray-500">Loading campaign detail...</div>
  if (!campaign) return <div className="p-8 text-red-500">Campaign not found</div>

  const totalSpend = metrics.reduce((s, m) => s + m.spend, 0)
  const totalRevenue = metrics.reduce((s, m) => s + m.revenue, 0)
  const totalConversions = metrics.reduce((s, m) => s + m.conversions, 0)
  const totalClicks = metrics.reduce((s, m) => s + m.clicks, 0)

  return (
    <div className="p-8 space-y-6">
      <div className="flex items-center gap-3">
        <Link href="/google/search" className="text-gray-400 hover:text-gray-600">&larr;</Link>
        <div>
          <h1 className="text-2xl font-bold text-gray-900">{campaign.name}</h1>
          <div className="flex items-center gap-3 mt-1">
            <span className="text-xs bg-green-50 text-green-700 px-2 py-0.5 rounded-full font-medium">SEARCH</span>
            <span className={`text-xs font-medium ${campaign.status === 'ACTIVE' ? 'text-green-600' : 'text-gray-400'}`}>
              {campaign.status}
            </span>
            {campaign.daily_budget && <span className="text-xs text-gray-500">${fmt(campaign.daily_budget)}/day</span>}
          </div>
        </div>
      </div>

      {/* KPI Summary */}
      <div className="grid grid-cols-5 gap-4">
        <div className="bg-white rounded-xl border p-4">
          <p className="text-xs text-gray-500">Spend</p>
          <p className="text-xl font-bold">${fmt(totalSpend)}</p>
        </div>
        <div className="bg-white rounded-xl border p-4">
          <p className="text-xs text-gray-500">Clicks</p>
          <p className="text-xl font-bold">{fmt(totalClicks)}</p>
        </div>
        <div className="bg-white rounded-xl border p-4">
          <p className="text-xs text-gray-500">Conversions</p>
          <p className="text-xl font-bold">{totalConversions}</p>
        </div>
        <div className="bg-white rounded-xl border p-4">
          <p className="text-xs text-gray-500">Revenue</p>
          <p className="text-xl font-bold">${fmt(totalRevenue)}</p>
        </div>
        <div className="bg-white rounded-xl border p-4">
          <p className="text-xs text-gray-500">ROAS</p>
          <p className="text-xl font-bold">{totalSpend > 0 ? (totalRevenue / totalSpend).toFixed(2) : '0'}x</p>
        </div>
      </div>

      {/* Ad Groups */}
      <div className="bg-white rounded-xl border border-gray-200">
        <div className="p-5 border-b border-gray-100">
          <h2 className="font-semibold text-gray-900">Ad Groups ({adGroups.length})</h2>
        </div>
        <div className="divide-y divide-gray-100">
          {adGroups.length === 0 ? (
            <div className="p-8 text-center text-gray-400">No ad groups found</div>
          ) : (
            adGroups.map(ag => (
              <div key={ag.id}>
                <button
                  onClick={() => loadAds(ag.id)}
                  className="w-full flex items-center justify-between px-5 py-4 hover:bg-gray-50 text-left"
                >
                  <div>
                    <p className="font-medium text-gray-900">{ag.name}</p>
                    {ag.country && <span className="text-xs text-gray-500">Country: {ag.country}</span>}
                  </div>
                  <span className={`text-xs font-medium ${ag.status === 'ACTIVE' ? 'text-green-600' : 'text-gray-400'}`}>
                    {ag.status}
                  </span>
                </button>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Daily Metrics Table */}
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
                  <th className="text-right px-5 py-3 text-gray-500 font-medium">Imp.</th>
                  <th className="text-right px-5 py-3 text-gray-500 font-medium">Clicks</th>
                  <th className="text-right px-5 py-3 text-gray-500 font-medium">CTR</th>
                  <th className="text-right px-5 py-3 text-gray-500 font-medium">Conv.</th>
                  <th className="text-right px-5 py-3 text-gray-500 font-medium">Revenue</th>
                  <th className="text-right px-5 py-3 text-gray-500 font-medium">ROAS</th>
                  <th className="text-right px-5 py-3 text-gray-500 font-medium">CPA</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {metrics.map(m => (
                  <tr key={m.date} className="hover:bg-gray-50">
                    <td className="px-5 py-3 text-gray-700">{m.date}</td>
                    <td className="px-5 py-3 text-right">${fmt(m.spend)}</td>
                    <td className="px-5 py-3 text-right">{fmt(m.impressions)}</td>
                    <td className="px-5 py-3 text-right">{fmt(m.clicks)}</td>
                    <td className="px-5 py-3 text-right">{m.ctr.toFixed(2)}%</td>
                    <td className="px-5 py-3 text-right">{m.conversions}</td>
                    <td className="px-5 py-3 text-right">${fmt(m.revenue)}</td>
                    <td className="px-5 py-3 text-right font-medium">{m.roas.toFixed(2)}x</td>
                    <td className="px-5 py-3 text-right">{m.cpa ? `$${fmt(m.cpa)}` : '-'}</td>
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
