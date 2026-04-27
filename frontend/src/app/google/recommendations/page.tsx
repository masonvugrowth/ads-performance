'use client'

import { useEffect, useMemo, useState } from 'react'
import RecommendationItem, {
  type RecCommonShape,
  type Severity,
  type Status,
} from '@/components/RecommendationItem'

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000'

type CampaignType = 'SEARCH' | 'PMAX' | 'DEMAND_GEN' | 'PORTFOLIO'

interface Account {
  id: string
  platform: string
  account_name: string
  currency: string
}

type GoogleRec = RecCommonShape & {
  account_id: string
  campaign_id: string | null
  ad_group_id: string | null
  ad_id: string | null
  asset_group_id: string | null
  campaign_type: CampaignType | null
}

export default function RecommendationsPage() {
  const [items, setItems] = useState<GoogleRec[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [accounts, setAccounts] = useState<Account[]>([])
  const [accountFilter, setAccountFilter] = useState<string>('all')
  const [statusFilter, setStatusFilter] = useState<Status | 'all'>('pending')
  const [severityFilter, setSeverityFilter] = useState<Severity | 'all'>('all')
  const [campaignTypeFilter, setCampaignTypeFilter] = useState<CampaignType | 'all'>('all')

  const [busyId, setBusyId] = useState<string | null>(null)
  const [busyMode, setBusyMode] = useState<'apply' | 'dismiss' | 'manual' | null>(null)

  useEffect(() => {
    fetch(`${API_BASE}/api/accounts`, { credentials: 'include' })
      .then(r => r.json())
      .then(res => {
        if (res.success) {
          const googleOnly = (res.data || []).filter((a: Account) => a.platform === 'google')
          setAccounts(googleOnly)
        }
      })
      .catch(() => {})
  }, [])

  const fetchList = () => {
    setLoading(true)
    const params = new URLSearchParams()
    if (statusFilter !== 'all') params.set('status', statusFilter)
    if (severityFilter !== 'all') params.set('severity', severityFilter)
    if (campaignTypeFilter !== 'all') params.set('campaign_type', campaignTypeFilter)
    if (accountFilter !== 'all') params.set('account_id', accountFilter)
    params.set('limit', '100')
    fetch(`${API_BASE}/api/google/recommendations?${params}`, { credentials: 'include' })
      .then(r => r.json())
      .then(res => {
        if (res.success) {
          setItems(res.data.items || [])
          setTotal(res.data.total || 0)
          setError(null)
        } else {
          setError(res.error || 'Failed to load recommendations')
        }
      })
      .catch(e => setError(String(e)))
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    fetchList()
  }, [statusFilter, severityFilter, campaignTypeFilter, accountFilter])

  const onApply = async (id: string) => {
    setBusyId(id)
    setBusyMode('apply')
    try {
      const r = await fetch(`${API_BASE}/api/google/recommendations/${id}/apply`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ confirm_warning: true }),
      })
      const res = await r.json()
      if (!r.ok || res.success === false) {
        alert(res.detail || res.error || `Apply failed (HTTP ${r.status})`)
        return
      }
      fetchList()
    } finally {
      setBusyId(null)
      setBusyMode(null)
    }
  }

  const onMarkManual = async (id: string, note: string) => {
    setBusyId(id)
    setBusyMode('manual')
    try {
      const r = await fetch(`${API_BASE}/api/google/recommendations/${id}/mark-manual`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ note }),
      })
      const res = await r.json()
      if (!r.ok || res.success === false) {
        alert(res.detail || res.error || `Mark manual failed (HTTP ${r.status})`)
        return
      }
      fetchList()
    } finally {
      setBusyId(null)
      setBusyMode(null)
    }
  }

  const onDismiss = async (id: string, reason: string) => {
    if (!reason) {
      alert('Please provide a dismiss reason.')
      return
    }
    setBusyId(id)
    setBusyMode('dismiss')
    try {
      const r = await fetch(`${API_BASE}/api/google/recommendations/${id}/dismiss`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason }),
      })
      const res = await r.json()
      if (!r.ok || res.success === false) {
        alert(res.detail || res.error || `Dismiss failed (HTTP ${r.status})`)
        return
      }
      fetchList()
    } finally {
      setBusyId(null)
      setBusyMode(null)
    }
  }

  const onRunNow = async () => {
    setLoading(true)
    try {
      for (const cadence of ['daily', 'weekly', 'monthly', 'seasonality']) {
        await fetch(`${API_BASE}/api/google/recommendations/run`, {
          method: 'POST',
          credentials: 'include',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ cadence }),
        })
      }
      fetchList()
    } finally {
      setLoading(false)
    }
  }

  const counts = useMemo(() => {
    const c: Record<Severity, number> = { critical: 0, warning: 0, info: 0 }
    items.forEach(it => { if (it.status === 'pending') c[it.severity]++ })
    return c
  }, [items])

  return (
    <div className="p-8">
      <header className="flex items-start justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Google Ads Recommendations</h1>
          <p className="text-sm text-gray-500 mt-1">
            SOP-driven optimization suggestions from the Power Pack engine.
          </p>
        </div>
        <button
          onClick={onRunNow}
          disabled={loading}
          className="px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 disabled:opacity-50"
          title="Run all cadences now (admin only)"
        >
          Run now
        </button>
      </header>

      <div className="grid grid-cols-3 gap-4 mb-6">
        <SummaryTile tone="red" label="Critical" value={counts.critical} />
        <SummaryTile tone="amber" label="Warning" value={counts.warning} />
        <SummaryTile tone="blue" label="Info" value={counts.info} />
      </div>

      <div className="flex gap-3 mb-4 flex-wrap">
        <Select label="Branch" value={accountFilter} onChange={setAccountFilter} options={[
          ['all', 'All branches'],
          ...accounts.map(a => [a.id, a.account_name] as [string, string]),
        ]} />
        <Select label="Status" value={statusFilter} onChange={v => setStatusFilter(v as any)} options={[
          ['all', 'All'], ['pending', 'Pending'], ['applied', 'Applied'],
          ['dismissed', 'Dismissed'], ['expired', 'Expired'], ['superseded', 'Superseded'],
          ['failed', 'Failed'],
        ]} />
        <Select label="Severity" value={severityFilter} onChange={v => setSeverityFilter(v as any)} options={[
          ['all', 'All'], ['critical', 'Critical'], ['warning', 'Warning'], ['info', 'Info'],
        ]} />
        <Select label="Campaign" value={campaignTypeFilter} onChange={v => setCampaignTypeFilter(v as any)} options={[
          ['all', 'All'], ['PMAX', 'PMax'], ['SEARCH', 'Search'],
          ['DEMAND_GEN', 'Demand Gen'], ['PORTFOLIO', 'Portfolio'],
        ]} />
        <div className="ml-auto text-sm text-gray-500 self-end">
          {loading ? 'Loading…' : `${items.length} of ${total}`}
        </div>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg mb-4">
          {error}
        </div>
      )}

      <div className="space-y-3" data-testid="rec-list">
        {items.length === 0 && !loading && (
          <div className="bg-white border border-gray-200 rounded-lg p-8 text-center text-gray-500">
            No recommendations match these filters.
          </div>
        )}
        {items.map(rec => (
          <RecommendationItem
            key={rec.id}
            rec={rec}
            platform="google"
            onApply={onApply}
            onDismiss={onDismiss}
            onMarkManual={onMarkManual}
            applyBusy={busyId === rec.id && busyMode === 'apply'}
            dismissBusy={busyId === rec.id && busyMode === 'dismiss'}
            manualBusy={busyId === rec.id && busyMode === 'manual'}
          />
        ))}
      </div>
    </div>
  )
}


function Select({
  label, value, onChange, options,
}: {
  label: string
  value: string
  onChange: (v: string) => void
  options: [string, string][]
}) {
  return (
    <div>
      <label className="block text-[10px] uppercase tracking-wider text-gray-400 font-semibold mb-1">
        {label}
      </label>
      <select
        value={value}
        onChange={e => onChange(e.target.value)}
        className="text-sm border border-gray-300 rounded px-2 py-1.5 bg-white"
      >
        {options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
      </select>
    </div>
  )
}


function SummaryTile({
  tone, label, value,
}: {
  tone: 'red' | 'amber' | 'blue'
  label: string
  value: number
}) {
  const map = {
    red: { border: 'border-red-200', text: 'text-red-700', label: 'text-red-600' },
    amber: { border: 'border-amber-200', text: 'text-amber-700', label: 'text-amber-600' },
    blue: { border: 'border-blue-200', text: 'text-blue-700', label: 'text-blue-600' },
  }[tone]
  return (
    <div className={`bg-white border ${map.border} rounded-lg p-4`}>
      <div className={`text-xs uppercase tracking-wider ${map.label} font-semibold`}>{label}</div>
      <div className={`text-3xl font-bold ${map.text} mt-2`}>{value}</div>
    </div>
  )
}
