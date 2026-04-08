'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000'

interface KPIs {
  total_spend: number
  total_impressions: number
  total_clicks: number
  total_conversions: number
  total_revenue: number
  roas: number
  ctr: number
  cpa: number | null
}

interface CampaignCounts {
  total: number
  performance_max: number
  search: number
  other: number
}

interface Campaign {
  id: string
  name: string
  status: string
  campaign_type: string
  daily_budget: number | null
  ta: string | null
  funnel_stage: string | null
}

export default function GoogleDashboard() {
  const [kpis, setKpis] = useState<KPIs | null>(null)
  const [counts, setCounts] = useState<CampaignCounts | null>(null)
  const [campaigns, setCampaigns] = useState<Campaign[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([
      fetch(`${API_BASE}/api/google/dashboard`, { credentials: 'include' }).then(r => r.json()),
      fetch(`${API_BASE}/api/google/campaigns?limit=20`, { credentials: 'include' }).then(r => r.json()),
    ]).then(([dashRes, campRes]) => {
      if (dashRes.success) {
        setKpis(dashRes.data.kpis)
        setCounts(dashRes.data.campaign_counts)
      }
      if (campRes.success) {
        setCampaigns(campRes.data.campaigns)
      }
    }).finally(() => setLoading(false))
  }, [])

  const fmt = (n: number) => n.toLocaleString('en-US', { maximumFractionDigits: 2 })
  const fmtCurrency = (n: number) => `$${fmt(n)}`

  if (loading) return <div className="p-8 text-gray-500">Loading Google Ads data...</div>

  return (
    <div className="p-8 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Google Ads Dashboard</h1>
          <p className="text-sm text-gray-500 mt-1">PMax + Search campaigns overview</p>
        </div>
        <button
          onClick={() => {
            fetch(`${API_BASE}/api/google/sync`, { method: 'POST', credentials: 'include' })
              .then(r => r.json())
              .then(() => window.location.reload())
          }}
          className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm"
        >
          Sync Google Ads
        </button>
      </div>

      {/* KPI Cards */}
      {kpis && (
        <div className="grid grid-cols-4 gap-4">
          {[
            { label: 'Total Spend', value: fmtCurrency(kpis.total_spend), color: 'blue' },
            { label: 'ROAS', value: `${kpis.roas.toFixed(2)}x`, color: 'green' },
            { label: 'CTR', value: `${kpis.ctr.toFixed(2)}%`, color: 'purple' },
            { label: 'CPA', value: kpis.cpa ? fmtCurrency(kpis.cpa) : 'N/A', color: 'orange' },
          ].map((card) => (
            <div key={card.label} className="bg-white rounded-xl border border-gray-200 p-5">
              <p className="text-xs text-gray-500 uppercase tracking-wider">{card.label}</p>
              <p className="text-2xl font-bold text-gray-900 mt-1">{card.value}</p>
            </div>
          ))}
        </div>
      )}

      {/* Metrics Row */}
      {kpis && (
        <div className="grid grid-cols-4 gap-4">
          <div className="bg-white rounded-xl border border-gray-200 p-4">
            <p className="text-xs text-gray-500">Impressions</p>
            <p className="text-lg font-semibold">{fmt(kpis.total_impressions)}</p>
          </div>
          <div className="bg-white rounded-xl border border-gray-200 p-4">
            <p className="text-xs text-gray-500">Clicks</p>
            <p className="text-lg font-semibold">{fmt(kpis.total_clicks)}</p>
          </div>
          <div className="bg-white rounded-xl border border-gray-200 p-4">
            <p className="text-xs text-gray-500">Conversions</p>
            <p className="text-lg font-semibold">{fmt(kpis.total_conversions)}</p>
          </div>
          <div className="bg-white rounded-xl border border-gray-200 p-4">
            <p className="text-xs text-gray-500">Revenue</p>
            <p className="text-lg font-semibold">{fmtCurrency(kpis.total_revenue)}</p>
          </div>
        </div>
      )}

      {/* Campaign Type Cards */}
      {counts && (
        <div className="grid grid-cols-3 gap-4">
          <Link href="/google/pmax" className="bg-white rounded-xl border border-gray-200 p-5 hover:border-blue-300 transition-colors">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-gray-500">Performance Max</p>
                <p className="text-3xl font-bold text-blue-600 mt-1">{counts.performance_max}</p>
              </div>
              <div className="w-12 h-12 bg-blue-50 rounded-lg flex items-center justify-center text-blue-600 text-xl">P</div>
            </div>
          </Link>
          <Link href="/google/search" className="bg-white rounded-xl border border-gray-200 p-5 hover:border-green-300 transition-colors">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-gray-500">Search</p>
                <p className="text-3xl font-bold text-green-600 mt-1">{counts.search}</p>
              </div>
              <div className="w-12 h-12 bg-green-50 rounded-lg flex items-center justify-center text-green-600 text-xl">S</div>
            </div>
          </Link>
          <div className="bg-white rounded-xl border border-gray-200 p-5">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-gray-500">Other (Display, Video, etc.)</p>
                <p className="text-3xl font-bold text-gray-600 mt-1">{counts.other}</p>
              </div>
              <div className="w-12 h-12 bg-gray-50 rounded-lg flex items-center justify-center text-gray-600 text-xl">O</div>
            </div>
          </div>
        </div>
      )}

      {/* Recent Campaigns */}
      <div className="bg-white rounded-xl border border-gray-200">
        <div className="p-5 border-b border-gray-200">
          <h2 className="font-semibold text-gray-900">Recent Campaigns</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-gray-50">
              <tr>
                <th className="text-left px-5 py-3 text-gray-500 font-medium">Name</th>
                <th className="text-left px-5 py-3 text-gray-500 font-medium">Type</th>
                <th className="text-left px-5 py-3 text-gray-500 font-medium">Status</th>
                <th className="text-left px-5 py-3 text-gray-500 font-medium">Budget</th>
                <th className="text-left px-5 py-3 text-gray-500 font-medium">TA</th>
                <th className="text-left px-5 py-3 text-gray-500 font-medium">Funnel</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {campaigns.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-5 py-10 text-center text-gray-400">
                    No Google campaigns synced yet. Add a Google Ads account and sync.
                  </td>
                </tr>
              ) : (
                campaigns.map((c) => (
                  <tr key={c.id} className="hover:bg-gray-50">
                    <td className="px-5 py-3">
                      <Link
                        href={c.campaign_type === 'PERFORMANCE_MAX' ? `/google/pmax/${c.id}` : `/google/search/${c.id}`}
                        className="text-blue-600 hover:underline font-medium"
                      >
                        {c.name}
                      </Link>
                    </td>
                    <td className="px-5 py-3">
                      <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${
                        c.campaign_type === 'PERFORMANCE_MAX'
                          ? 'bg-blue-50 text-blue-700'
                          : c.campaign_type === 'SEARCH'
                          ? 'bg-green-50 text-green-700'
                          : 'bg-gray-50 text-gray-700'
                      }`}>
                        {c.campaign_type}
                      </span>
                    </td>
                    <td className="px-5 py-3">
                      <span className={`text-xs font-medium ${
                        c.status === 'ACTIVE' ? 'text-green-600' : 'text-gray-400'
                      }`}>
                        {c.status}
                      </span>
                    </td>
                    <td className="px-5 py-3 text-gray-600">
                      {c.daily_budget ? fmtCurrency(c.daily_budget) : '-'}
                    </td>
                    <td className="px-5 py-3 text-gray-600">{c.ta || '-'}</td>
                    <td className="px-5 py-3 text-gray-600">{c.funnel_stage || '-'}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
