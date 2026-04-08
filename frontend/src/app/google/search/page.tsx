'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000'

interface Campaign {
  id: string
  name: string
  status: string
  daily_budget: number | null
  ta: string | null
  funnel_stage: string | null
}

export default function SearchCampaignsPage() {
  const [campaigns, setCampaigns] = useState<Campaign[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch(`${API_BASE}/api/google/campaigns?campaign_type=SEARCH&limit=100`, { credentials: 'include' })
      .then(r => r.json())
      .then(data => {
        if (data.success) setCampaigns(data.data.campaigns)
      })
      .finally(() => setLoading(false))
  }, [])

  const fmtCurrency = (n: number) => `$${n.toLocaleString('en-US', { maximumFractionDigits: 2 })}`

  if (loading) return <div className="p-8 text-gray-500">Loading Search campaigns...</div>

  return (
    <div className="p-8 space-y-6">
      <div className="flex items-center gap-3">
        <Link href="/google" className="text-gray-400 hover:text-gray-600">&larr;</Link>
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Search Campaigns</h1>
          <p className="text-sm text-gray-500">{campaigns.length} campaigns</p>
        </div>
      </div>

      <div className="bg-white rounded-xl border border-gray-200">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-gray-50">
              <tr>
                <th className="text-left px-5 py-3 text-gray-500 font-medium">Campaign Name</th>
                <th className="text-left px-5 py-3 text-gray-500 font-medium">Status</th>
                <th className="text-left px-5 py-3 text-gray-500 font-medium">Budget</th>
                <th className="text-left px-5 py-3 text-gray-500 font-medium">TA</th>
                <th className="text-left px-5 py-3 text-gray-500 font-medium">Funnel</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {campaigns.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-5 py-10 text-center text-gray-400">
                    No Search campaigns found
                  </td>
                </tr>
              ) : (
                campaigns.map(c => (
                  <tr key={c.id} className="hover:bg-gray-50">
                    <td className="px-5 py-3">
                      <Link href={`/google/search/${c.id}`} className="text-blue-600 hover:underline font-medium">
                        {c.name}
                      </Link>
                    </td>
                    <td className="px-5 py-3">
                      <span className={`text-xs font-medium ${c.status === 'ACTIVE' ? 'text-green-600' : 'text-gray-400'}`}>
                        {c.status}
                      </span>
                    </td>
                    <td className="px-5 py-3 text-gray-600">{c.daily_budget ? fmtCurrency(c.daily_budget) : '-'}</td>
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
