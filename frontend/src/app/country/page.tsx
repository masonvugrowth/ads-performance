'use client'

import { useEffect, useState, useCallback, useRef, Suspense } from 'react'
import { useSearchParams } from 'next/navigation'
import { TrendingUp, TrendingDown, ArrowUp, ArrowDown, ArrowUpDown, ChevronRight, Activity, BarChart3, Sparkles } from 'lucide-react'
import { apiFetch } from '@/lib/api'
import { useSortableRows } from '@/lib/useSortableRows'
import ActivityLogPanel from './ActivityLogPanel'
import ManualEntryModal from './ManualEntryModal'

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000'

const CURRENCY_SYMBOLS: Record<string, string> = {
  VND: '₫', TWD: 'NT$', JPY: '¥', USD: '$',
}

function fmtMoney(n: number, currency: string): string {
  const symbol = CURRENCY_SYMBOLS[currency] || currency
  return `${new Intl.NumberFormat('vi-VN', { maximumFractionDigits: 0 }).format(n)} ${symbol}`
}

type CountryOption = { code: string; name: string; adset_count: number }
type Branch = { name: string; currency: string }

type CampaignRow = {
  campaign_id: string
  campaign_name: string
  campaign_status: string
  funnel_stage: string | null
  ta: string | null
  platform: string
  account_name: string
  spend: number
  revenue: number
  impressions: number
  clicks: number
  conversions: number
  roas: number
  ctr: number
  cpc: number
  cpa: number
  cr: number
  aov: number
  spend_change: number | null
  roas_change: number | null
  cr_change: number | null
  aov_change: number | null
  cpc_change: number | null
  conversions_change: number | null
}

type CountryKpi = {
  country_code: string
  country: string
  total_spend: number
  total_revenue: number
  roas: number
  ctr: number
  cpa: number
  impressions: number
  clicks: number
  conversions: number
  campaign_count: number
  spend_change: number | null
  revenue_change: number | null
  roas_change: number | null
  ctr_change: number | null
  cpa_change: number | null
  conversions_change: number | null
}

type TaRow = {
  ta: string
  funnel_stage: string
  spend: number
  revenue: number
  roas: number
  ctr: number
  cpa: number
  conversions: number
  is_remarketing: boolean
  spend_change: number | null
  roas_change: number | null
  conversions_change: number | null
}

type FunnelStage = {
  name: string
  value: number
  change: number | null
  drop_off: number | null
  drop_off_change: number | null
}

function ChangeTag({ change, inverseColor = false }: { change: number | null; inverseColor?: boolean }) {
  if (change === null || change === undefined) return <span className="text-xs text-gray-400">--</span>
  const pct = change * 100
  if (Math.abs(pct) < 0.01) return <span className="text-xs text-gray-400">0%</span>
  const pos = pct > 0
  const isGood = inverseColor ? !pos : pos
  return (
    <span className={`inline-flex items-center gap-0.5 text-xs font-medium ${isGood ? 'text-green-600' : 'text-red-500'}`}>
      {pos ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
      {pos ? '+' : ''}{pct.toFixed(1)}%
    </span>
  )
}

function getDateRange(preset: string): { from: string; to: string } {
  const today = new Date()
  const to = today.toISOString().split('T')[0]
  const daysBack = (d: number) => {
    const dt = new Date(today)
    dt.setDate(dt.getDate() - d)
    return dt.toISOString().split('T')[0]
  }
  switch (preset) {
    case 'today': return { from: to, to }
    case 'yesterday': {
      const y = daysBack(1)
      return { from: y, to: y }
    }
    case '7d': return { from: daysBack(6), to }
    case '14d': return { from: daysBack(13), to }
    case '30d': return { from: daysBack(29), to }
    case 'this_month': {
      const from = new Date(today.getFullYear(), today.getMonth(), 1).toISOString().split('T')[0]
      return { from, to }
    }
    case 'last_month': {
      const from = new Date(today.getFullYear(), today.getMonth() - 1, 1).toISOString().split('T')[0]
      const last = new Date(today.getFullYear(), today.getMonth(), 0).toISOString().split('T')[0]
      return { from, to: last }
    }
    default: return { from: daysBack(6), to }
  }
}

const fmt = (n: number) => new Intl.NumberFormat('vi-VN', { maximumFractionDigits: 0 }).format(n)

function CountryDashboardInner() {
  const search = useSearchParams()
  // Deep-link inputs from /meta/recommendations card. The page reads these
  // once on mount, then ignores subsequent URL changes so user filter edits
  // don't fight the URL.
  const initialBranches = (search.get('branches') || '').split(',').map(s => s.trim()).filter(Boolean)
  const initialCountry = (search.get('country') || '').toUpperCase()
  const initialPlatform = (search.get('platform') || '').toLowerCase()
  const initialFunnel = (search.get('funnel') || '').toUpperCase()
  const initialRange = search.get('range') || '7d'
  const highlightCampaignId = search.get('campaign') || ''

  const [country, setCountry] = useState(initialCountry)
  const [platform, setPlatform] = useState(initialPlatform)
  const [funnelStage, setFunnelStage] = useState(initialFunnel)
  const [selectedBranches, setSelectedBranches] = useState<string[]>(initialBranches)
  const [branchDropdownOpen, setBranchDropdownOpen] = useState(false)
  const [datePreset, setDatePreset] = useState(initialRange)
  const [customFrom, setCustomFrom] = useState('')
  const [customTo, setCustomTo] = useState('')

  const [countries, setCountries] = useState<CountryOption[]>([])
  const [branches, setBranches] = useState<Branch[]>([])
  const [kpiData, setKpiData] = useState<CountryKpi[]>([])
  const [taData, setTaData] = useState<TaRow[]>([])
  const [campaignRows, setCampaignRows] = useState<CampaignRow[]>([])
  const [funnelData, setFunnelData] = useState<FunnelStage[]>([])
  const [comparison, setComparison] = useState<CountryKpi[]>([])
  const [responseCurrency, setResponseCurrency] = useState<string>('VND')
  const [periodInfo, setPeriodInfo] = useState<{ from: string; to: string; prev_from: string; prev_to: string } | null>(null)
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState<'overview' | 'activity'>('overview')
  const [manualModalOpen, setManualModalOpen] = useState(false)
  const [activityRefreshKey, setActivityRefreshKey] = useState(0)
  const [canEditAnalytics, setCanEditAnalytics] = useState(false)

  // Detect whether the current user can add manual entries (analytics-edit).
  useEffect(() => {
    apiFetch<{ is_admin: boolean; accessible_sections?: Record<string, string[]>; permissions?: Array<{ section: string; level: string }> }>('/api/auth/me')
      .then((res) => {
        if (!res.success || !res.data) return
        if (res.data.is_admin) {
          setCanEditAnalytics(true)
          return
        }
        const hasEdit = (res.data.permissions || []).some(
          (p) => p.section === 'analytics' && p.level === 'edit',
        )
        setCanEditAnalytics(hasEdit)
      })
      .catch(() => {})
  }, [])

  // Load branches once
  useEffect(() => {
    fetch(`${API_BASE}/api/branches`, { credentials: 'include' })
      .then(r => r.json())
      .then(data => { if (data.success) setBranches(data.data) })
      .catch(() => {})
  }, [])

  const branchParam = selectedBranches.length > 0 ? selectedBranches.join(',') : ''

  // Load countries (filtered by branches)
  useEffect(() => {
    const qp = branchParam ? `?branches=${encodeURIComponent(branchParam)}` : ''
    fetch(`${API_BASE}/api/dashboard/country/countries${qp}`, { credentials: 'include' })
      .then(r => r.json())
      .then(res => { if (res.success) setCountries(res.data) })
      .catch(() => {})
  }, [branchParam])

  const branchDropdownRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (branchDropdownRef.current && !branchDropdownRef.current.contains(e.target as Node)) {
        setBranchDropdownOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  const toggleBranch = (name: string) => {
    setSelectedBranches(prev =>
      prev.includes(name) ? prev.filter(b => b !== name) : [...prev, name]
    )
  }

  const activeCurrency = (() => {
    if (selectedBranches.length === 0) return 'VND'
    const currencies = [...new Set(selectedBranches.map(b => branches.find(br => br.name === b)?.currency || 'VND'))]
    return currencies.length === 1 ? currencies[0] : 'VND'
  })()

  const resolvedRange = useCallback(() => {
    if (datePreset === 'custom' && customFrom && customTo) {
      return { from: customFrom, to: customTo }
    }
    return getDateRange(datePreset)
  }, [datePreset, customFrom, customTo])

  const buildQs = useCallback(() => {
    const { from, to } = resolvedRange()
    const params = new URLSearchParams({ date_from: from, date_to: to })
    if (country) params.set('country', country)
    if (platform) params.set('platform', platform)
    if (funnelStage) params.set('funnel_stage', funnelStage)
    if (branchParam) params.set('branches', branchParam)
    return params.toString()
  }, [country, platform, funnelStage, branchParam, resolvedRange])

  useEffect(() => {
    if (datePreset === 'custom' && (!customFrom || !customTo)) return
    setLoading(true)
    const qs = buildQs()
    const { from, to } = resolvedRange()

    const taQs = country
      ? `country=${country}&date_from=${from}&date_to=${to}${platform ? `&platform=${platform}` : ''}${branchParam ? `&branches=${encodeURIComponent(branchParam)}` : ''}`
      : null

    Promise.all([
      fetch(`${API_BASE}/api/dashboard/country?${qs}`, { credentials: 'include' }).then(r => r.json()),
      fetch(`${API_BASE}/api/dashboard/country/comparison?${qs}`, { credentials: 'include' }).then(r => r.json()),
      taQs
        ? fetch(`${API_BASE}/api/dashboard/country/ta-breakdown?${taQs}`, { credentials: 'include' }).then(r => r.json())
        : Promise.resolve({ success: true, data: [] }),
      taQs
        ? fetch(`${API_BASE}/api/dashboard/country/funnel?${taQs}`, { credentials: 'include' }).then(r => r.json())
        : Promise.resolve({ success: true, data: { stages: [] } }),
      fetch(`${API_BASE}/api/dashboard/country/campaigns?${qs}`, { credentials: 'include' }).then(r => r.json()),
    ]).then(([kpi, comp, ta, funnel, campaigns]) => {
      if (kpi.success && kpi.data) {
        setKpiData(kpi.data.items || [])
        setResponseCurrency(kpi.data.currency || 'VND')
        if (kpi.data.period) {
          setPeriodInfo({
            from: kpi.data.period.from,
            to: kpi.data.period.to,
            prev_from: kpi.data.prev_period.from,
            prev_to: kpi.data.prev_period.to,
          })
        }
      }
      if (comp.success) setComparison(comp.data || [])
      if (ta.success) setTaData(Array.isArray(ta.data) ? ta.data : [])
      if (funnel.success) setFunnelData(funnel.data?.stages || [])
      if (campaigns.success) setCampaignRows(campaigns.data?.items || [])
      setLoading(false)
    }).catch(() => setLoading(false))
  }, [buildQs, datePreset, country, platform, branchParam])

  // Aggregate KPIs when no country is selected
  const aggregatedKpi = kpiData.length > 0 ? kpiData.reduce((acc, k) => ({
    total_spend: acc.total_spend + k.total_spend,
    total_revenue: acc.total_revenue + k.total_revenue,
    impressions: acc.impressions + k.impressions,
    clicks: acc.clicks + k.clicks,
    conversions: acc.conversions + k.conversions,
    campaign_count: acc.campaign_count + k.campaign_count,
  }), { total_spend: 0, total_revenue: 0, impressions: 0, clicks: 0, conversions: 0, campaign_count: 0 }) : null

  const selectedKpi = country
    ? kpiData.find(k => k.country_code === country)
    : aggregatedKpi

  return (
    <div>
      {/* Header + Filters */}
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <h1 className="text-2xl font-bold text-blue-600">Country Dashboard</h1>
        <div className="flex flex-wrap items-center gap-2">
          <select value={datePreset} onChange={e => setDatePreset(e.target.value)}
            className="px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500">
            <option value="today">Today</option>
            <option value="yesterday">Yesterday</option>
            <option value="7d">Last 7 days</option>
            <option value="14d">Last 14 days</option>
            <option value="30d">Last 30 days</option>
            <option value="this_month">This month</option>
            <option value="last_month">Last month</option>
            <option value="custom">Custom range</option>
          </select>
          {datePreset === 'custom' && (
            <>
              <input
                type="date"
                value={customFrom}
                onChange={(e) => setCustomFrom(e.target.value)}
                className="px-2 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <span className="text-gray-400">→</span>
              <input
                type="date"
                value={customTo}
                onChange={(e) => setCustomTo(e.target.value)}
                className="px-2 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </>
          )}
          <div className="relative" ref={branchDropdownRef}>
            <button
              onClick={() => setBranchDropdownOpen(!branchDropdownOpen)}
              className="px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white min-w-[180px] text-left flex items-center justify-between gap-2"
            >
              <span className="truncate">
                {selectedBranches.length === 0
                  ? `All Branches (VND)`
                  : selectedBranches.length === 1
                    ? `${selectedBranches[0]} (${activeCurrency})`
                    : `${selectedBranches.length} branches (${activeCurrency})`}
              </span>
              <svg className={`w-4 h-4 text-gray-400 transition-transform ${branchDropdownOpen ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" /></svg>
            </button>
            {branchDropdownOpen && (
              <div className="absolute z-50 mt-1 w-56 bg-white border border-gray-200 rounded-lg shadow-lg py-1">
                {selectedBranches.length > 0 && (
                  <button
                    onClick={() => setSelectedBranches([])}
                    className="w-full px-3 py-1.5 text-xs text-blue-600 hover:bg-gray-50 text-left"
                  >
                    Clear all
                  </button>
                )}
                {branches.map(b => (
                  <label
                    key={b.name}
                    className="flex items-center gap-2 px-3 py-2 hover:bg-gray-50 cursor-pointer text-sm"
                  >
                    <input
                      type="checkbox"
                      checked={selectedBranches.includes(b.name)}
                      onChange={() => toggleBranch(b.name)}
                      className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                    />
                    <span>{b.name}</span>
                    <span className="text-gray-400 text-xs ml-auto">{b.currency}</span>
                  </label>
                ))}
              </div>
            )}
          </div>
          <select value={country} onChange={e => setCountry(e.target.value)}
            className="px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500">
            <option value="">All Markets</option>
            {countries.map(c => (
              <option key={c.code} value={c.code}>{c.name}</option>
            ))}
          </select>
          <select value={platform} onChange={e => setPlatform(e.target.value)}
            className="px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500">
            <option value="">All Platforms</option>
            <option value="meta">Meta</option>
            <option value="google">Google</option>
            <option value="tiktok">TikTok</option>
          </select>
          <select value={funnelStage} onChange={e => setFunnelStage(e.target.value)}
            className="px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500">
            <option value="">All Funnel</option>
            <option value="TOF">TOF (Cold)</option>
            <option value="MOF">MOF (Remarketing)</option>
            <option value="BOF">BOF (Bottom)</option>
          </select>
        </div>
      </div>

      {/* Period info */}
      {periodInfo && (
        <p className="text-xs text-gray-400 mb-4">
          {periodInfo.from} → {periodInfo.to} &nbsp;vs&nbsp; {periodInfo.prev_from} → {periodInfo.prev_to}
        </p>
      )}

      {loading ? (
        <div className="flex items-center justify-center h-64"><div className="text-gray-500">Loading dashboard...</div></div>
      ) : (
        <div className="space-y-6">
          {/* KPI Summary (shown on both tabs). Two rows so the labels never
              wrap: row 1 = headline metrics; row 2 = the ROAS = CR × AOV /
              CPC decomposition the user opens this dashboard from a rec to
              diagnose. */}
          {selectedKpi && (() => {
            const cr = selectedKpi.clicks ? (selectedKpi.conversions / selectedKpi.clicks) * 100 : 0
            const aov = selectedKpi.conversions ? selectedKpi.total_revenue / selectedKpi.conversions : 0
            const cpc = selectedKpi.clicks ? selectedKpi.total_spend / selectedKpi.clicks : 0
            const headline = [
              { label: `Spend (${responseCurrency})`, value: fmtMoney(selectedKpi.total_spend, responseCurrency), change: country ? kpiData.find(k => k.country_code === country)?.spend_change : null, inverse: true },
              { label: `Revenue (${responseCurrency})`, value: fmtMoney(selectedKpi.total_revenue, responseCurrency), change: country ? kpiData.find(k => k.country_code === country)?.revenue_change : null, inverse: false },
              { label: 'ROAS', value: selectedKpi.total_spend ? (selectedKpi.total_revenue / selectedKpi.total_spend).toFixed(2) + 'x' : '0', change: country ? kpiData.find(k => k.country_code === country)?.roas_change : null, inverse: false },
              { label: 'CTR', value: selectedKpi.impressions ? ((selectedKpi.clicks / selectedKpi.impressions) * 100).toFixed(1) + '%' : '0%', change: country ? kpiData.find(k => k.country_code === country)?.ctr_change ?? null : null, inverse: false },
              { label: `CPA (${responseCurrency})`, value: selectedKpi.conversions ? fmtMoney(Math.round(selectedKpi.total_spend / selectedKpi.conversions), responseCurrency) : '--', change: country ? kpiData.find(k => k.country_code === country)?.cpa_change ?? null : null, inverse: true },
              { label: 'Campaigns', value: String(selectedKpi.campaign_count), change: null, inverse: false },
            ]
            const decomp = [
              { label: 'CR (Conversion Rate)', value: cr ? cr.toFixed(2) + '%' : '--', change: null, inverse: false },
              { label: `AOV (${responseCurrency})`, value: aov ? fmtMoney(Math.round(aov), responseCurrency) : '--', change: null, inverse: false },
              { label: `CPC (${responseCurrency})`, value: cpc ? fmtMoney(Math.round(cpc), responseCurrency) : '--', change: null, inverse: true },
            ]
            const renderCard = (kpi: typeof headline[number]) => (
              <div key={kpi.label} className="bg-white rounded-xl border border-gray-200 p-5">
                <p className="text-xs text-gray-500 mb-1 truncate">{kpi.label}</p>
                <p className="text-2xl font-bold text-gray-900">{kpi.value}</p>
                <div className="mt-2"><ChangeTag change={kpi.change ?? null} inverseColor={kpi.inverse} /></div>
              </div>
            )
            return (
              <div className="space-y-4">
                <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
                  {headline.map(renderCard)}
                </div>
                <div>
                  <div className="flex items-center gap-2 mb-2 text-[11px] uppercase tracking-wider text-gray-400 font-semibold">
                    ROAS decomposition
                    <span className="text-gray-300 normal-case font-normal tracking-normal">
                      ROAS = CR × AOV / CPC
                    </span>
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    {decomp.map(renderCard)}
                  </div>
                </div>
              </div>
            )
          })()}

          {/* Tab switcher */}
          <div className="flex items-center border-b border-gray-200">
            <button
              onClick={() => setActiveTab('overview')}
              className={`inline-flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors ${
                activeTab === 'overview'
                  ? 'border-blue-600 text-blue-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700'
              }`}
            >
              <BarChart3 className="w-4 h-4" />
              Overview
            </button>
            <button
              onClick={() => setActiveTab('activity')}
              className={`inline-flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors ${
                activeTab === 'activity'
                  ? 'border-blue-600 text-blue-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700'
              }`}
            >
              <Activity className="w-4 h-4" />
              Activity Log
            </button>
          </div>

          {/* TA Breakdown Table (Overview only) */}
          {activeTab === 'overview' && country && taData.length > 0 && (
            <TaBreakdownTable
              rows={taData}
              currency={responseCurrency}
              title={`TA Breakdown — ${countries.find(c => c.code === country)?.name || country}`}
            />
          )}

          {/* Campaign Breakdown — surfaces per-campaign CR/AOV/CPC so the user
              can see which factor is dragging ROAS. Highlights the campaign
              passed via ?campaign=<id> from a recommendation deep-link. */}
          {activeTab === 'overview' && campaignRows.length > 0 && (
            <CampaignBreakdownTable
              rows={campaignRows}
              currency={responseCurrency}
              highlightId={highlightCampaignId}
              title={
                country
                  ? `Campaign Breakdown — ${countries.find(c => c.code === country)?.name || country}`
                  : 'Campaign Breakdown'
              }
            />
          )}

          {/* Conversion Funnel (Overview only) */}
          {activeTab === 'overview' && country && funnelData.length > 0 && (
            <div className="bg-white rounded-xl border border-gray-200 p-6">
              <h2 className="text-sm font-semibold text-gray-700 mb-5">
                Conversion Funnel — {countries.find(c => c.code === country)?.name || country}
              </h2>
              <div className="space-y-3">
                {funnelData.map((stage, i) => {
                  const maxVal = Math.max(...funnelData.map(s => s.value), 1)
                  const widthPct = Math.max((stage.value / maxVal) * 100, 4)
                  return (
                    <div key={stage.name}>
                      {i > 0 && (
                        <div className="flex items-center gap-2 ml-4 mb-1">
                          <ChevronRight className="w-3 h-3 text-gray-300" />
                          {stage.drop_off !== null && (
                            <span className="text-xs text-gray-400">
                              {(stage.drop_off * 100).toFixed(1)}% drop-off
                            </span>
                          )}
                          {stage.drop_off_change !== null && (
                            <ChangeTag change={stage.drop_off_change} inverseColor />
                          )}
                        </div>
                      )}
                      <div className="flex items-center gap-4">
                        <div className="bg-blue-100 rounded-lg py-3 px-4 flex items-center justify-between transition-all"
                          style={{ width: `${widthPct}%`, minWidth: '180px' }}>
                          <span className="text-xs text-gray-600">{stage.name}</span>
                          <span className="text-lg font-bold text-gray-900 ml-2">{fmt(stage.value)}</span>
                        </div>
                        <ChangeTag change={stage.change} />
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          {/* Country Comparison Table (Overview only) */}
          {activeTab === 'overview' && comparison.length > 0 && (
            <CountryComparisonTable rows={comparison} currency={responseCurrency} />
          )}

          {/* Activity Log tab content */}
          {activeTab === 'activity' && (
            <ActivityLogPanel
              country={country}
              branches={branchParam}
              platform={platform}
              dateFrom={resolvedRange().from}
              dateTo={resolvedRange().to}
              canEdit={canEditAnalytics}
              onAddManual={() => setManualModalOpen(true)}
              refreshKey={activityRefreshKey}
            />
          )}

          {activeTab === 'overview' && !loading && kpiData.length === 0 && (
            <div className="text-center py-12 text-gray-400">
              No data available. Run a sync first to populate metrics.
            </div>
          )}
        </div>
      )}

      {manualModalOpen && (
        <ManualEntryModal
          open={manualModalOpen}
          onClose={() => setManualModalOpen(false)}
          onCreated={() => {
            setActivityRefreshKey((k) => k + 1)
            setManualModalOpen(false)
          }}
          defaultCountry={country || null}
          defaultBranch={selectedBranches.length === 1 ? selectedBranches[0] : null}
          branches={branches}
          countries={countries}
        />
      )}
    </div>
  )
}

function SortableTh<T extends Record<string, any>>({
  col, label, align = 'right', sortBy, sortDir, onToggle,
}: {
  col: keyof T
  label: string
  align?: 'left' | 'right'
  sortBy: keyof T | null
  sortDir: 'asc' | 'desc'
  onToggle: (c: keyof T) => void
}) {
  const active = sortBy === col
  return (
    <th
      className={`${align === 'right' ? 'text-right' : 'text-left'} py-3 px-4 text-gray-500 font-medium cursor-pointer select-none hover:text-gray-700`}
      onClick={() => onToggle(col)}
    >
      <span className={`inline-flex items-center gap-1 ${align === 'right' ? 'justify-end w-full' : ''}`}>
        {label}
        {active
          ? (sortDir === 'asc' ? <ArrowUp className="w-3 h-3" /> : <ArrowDown className="w-3 h-3" />)
          : <ArrowUpDown className="w-3 h-3 opacity-40" />}
      </span>
    </th>
  )
}

function TaBreakdownTable({ rows, title, currency }: { rows: TaRow[]; title: string; currency: string }) {
  const { sorted, sortBy, sortDir, toggleSort } = useSortableRows<TaRow>(rows, 'roas', 'desc')
  return (
    <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
      <div className="px-6 py-4 border-b">
        <h2 className="text-sm font-semibold text-gray-700">{title}</h2>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-100">
              <SortableTh<TaRow> col="ta" label="TA" align="left" sortBy={sortBy} sortDir={sortDir} onToggle={toggleSort} />
              <SortableTh<TaRow> col="funnel_stage" label="Funnel" align="left" sortBy={sortBy} sortDir={sortDir} onToggle={toggleSort} />
              <SortableTh<TaRow> col="spend" label={`Spend (${currency})`} sortBy={sortBy} sortDir={sortDir} onToggle={toggleSort} />
              <SortableTh<TaRow> col="revenue" label={`Revenue (${currency})`} sortBy={sortBy} sortDir={sortDir} onToggle={toggleSort} />
              <SortableTh<TaRow> col="roas" label="ROAS" sortBy={sortBy} sortDir={sortDir} onToggle={toggleSort} />
              <SortableTh<TaRow> col="ctr" label="CTR" sortBy={sortBy} sortDir={sortDir} onToggle={toggleSort} />
              <SortableTh<TaRow> col="cpa" label={`CPA (${currency})`} sortBy={sortBy} sortDir={sortDir} onToggle={toggleSort} />
              <SortableTh<TaRow> col="conversions" label="Conv" sortBy={sortBy} sortDir={sortDir} onToggle={toggleSort} />
            </tr>
          </thead>
          <tbody>
            {sorted.map((row) => (
              <tr key={`${row.ta}-${row.funnel_stage}`}
                className={`border-b border-gray-50 ${row.is_remarketing ? 'bg-amber-50' : 'hover:bg-gray-50'}`}>
                <td className="py-3 px-4 font-medium text-gray-900">{row.ta}</td>
                <td className="py-3 px-4">
                  <span className={`text-xs px-2 py-0.5 rounded-full ${
                    row.funnel_stage === 'TOF' ? 'bg-blue-100 text-blue-700' :
                    row.funnel_stage === 'MOF' ? 'bg-amber-100 text-amber-700' :
                    row.funnel_stage === 'BOF' ? 'bg-green-100 text-green-700' :
                    'bg-gray-100 text-gray-700'
                  }`}>{row.funnel_stage}</span>
                </td>
                <td className="py-3 px-4 text-right">
                  <div>{fmtMoney(row.spend, currency)}</div>
                  <ChangeTag change={row.spend_change} inverseColor />
                </td>
                <td className="py-3 px-4 text-right">{fmtMoney(row.revenue, currency)}</td>
                <td className="py-3 px-4 text-right">
                  <div className={`font-medium ${row.roas >= 1 ? 'text-green-600' : 'text-red-600'}`}>{row.roas.toFixed(2)}x</div>
                  <ChangeTag change={row.roas_change} />
                </td>
                <td className="py-3 px-4 text-right">{row.ctr.toFixed(1)}%</td>
                <td className="py-3 px-4 text-right">{fmtMoney(Math.round(row.cpa), currency)}</td>
                <td className="py-3 px-4 text-right">
                  <div>{row.conversions}</div>
                  <ChangeTag change={row.conversions_change} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function CampaignBreakdownTable({
  rows, currency, highlightId, title,
}: {
  rows: CampaignRow[]
  currency: string
  highlightId: string
  title: string
}) {
  const { sorted, sortBy, sortDir, toggleSort } = useSortableRows<CampaignRow>(rows, 'spend', 'desc')
  // Float the highlighted (deep-linked) campaign to the top regardless of sort.
  const ordered = highlightId
    ? [
      ...sorted.filter(r => r.campaign_id === highlightId),
      ...sorted.filter(r => r.campaign_id !== highlightId),
    ]
    : sorted
  const highlightRef = useRef<HTMLTableRowElement>(null)
  useEffect(() => {
    if (highlightId && highlightRef.current) {
      highlightRef.current.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }
  }, [highlightId, rows.length])

  return (
    <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
      <div className="px-6 py-4 border-b flex items-center justify-between">
        <h2 className="text-sm font-semibold text-gray-700">{title}</h2>
        <span className="text-[11px] text-gray-400">ROAS = CR × AOV / CPC</span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-100">
              <SortableTh<CampaignRow> col="campaign_name" label="Campaign" align="left" sortBy={sortBy} sortDir={sortDir} onToggle={toggleSort} />
              <SortableTh<CampaignRow> col="funnel_stage" label="Funnel" align="left" sortBy={sortBy} sortDir={sortDir} onToggle={toggleSort} />
              <SortableTh<CampaignRow> col="spend" label={`Spend (${currency})`} sortBy={sortBy} sortDir={sortDir} onToggle={toggleSort} />
              <SortableTh<CampaignRow> col="revenue" label={`Revenue (${currency})`} sortBy={sortBy} sortDir={sortDir} onToggle={toggleSort} />
              <SortableTh<CampaignRow> col="roas" label="ROAS" sortBy={sortBy} sortDir={sortDir} onToggle={toggleSort} />
              <SortableTh<CampaignRow> col="cr" label="CR" sortBy={sortBy} sortDir={sortDir} onToggle={toggleSort} />
              <SortableTh<CampaignRow> col="aov" label={`AOV (${currency})`} sortBy={sortBy} sortDir={sortDir} onToggle={toggleSort} />
              <SortableTh<CampaignRow> col="cpc" label={`CPC (${currency})`} sortBy={sortBy} sortDir={sortDir} onToggle={toggleSort} />
              <SortableTh<CampaignRow> col="conversions" label="Conv" sortBy={sortBy} sortDir={sortDir} onToggle={toggleSort} />
            </tr>
          </thead>
          <tbody>
            {ordered.map(row => {
              const isHighlight = row.campaign_id === highlightId
              return (
                <tr
                  key={row.campaign_id}
                  ref={isHighlight ? highlightRef : null}
                  className={`border-b border-gray-50 ${
                    isHighlight
                      ? 'bg-blue-50 ring-2 ring-inset ring-blue-300'
                      : 'hover:bg-gray-50'
                  }`}
                >
                  <td className="py-3 px-4">
                    <div className="flex items-center gap-2">
                      {isHighlight && (
                        <span className="inline-flex items-center gap-1 text-[10px] font-semibold text-blue-700 bg-blue-100 px-1.5 py-0.5 rounded">
                          <Sparkles className="w-3 h-3" /> from rec
                        </span>
                      )}
                      <span className="font-medium text-gray-900 break-words" title={row.campaign_name}>
                        {row.campaign_name}
                      </span>
                    </div>
                    <div className="text-[11px] text-gray-400 mt-0.5">
                      {[row.account_name, row.platform, row.ta].filter(Boolean).join(' · ')}
                    </div>
                  </td>
                  <td className="py-3 px-4">
                    {row.funnel_stage && (
                      <span className={`text-xs px-2 py-0.5 rounded-full ${
                        row.funnel_stage === 'TOF' ? 'bg-blue-100 text-blue-700' :
                        row.funnel_stage === 'MOF' ? 'bg-amber-100 text-amber-700' :
                        row.funnel_stage === 'BOF' ? 'bg-green-100 text-green-700' :
                        'bg-gray-100 text-gray-700'
                      }`}>{row.funnel_stage}</span>
                    )}
                  </td>
                  <td className="py-3 px-4 text-right">
                    <div>{fmtMoney(row.spend, currency)}</div>
                    <ChangeTag change={row.spend_change} inverseColor />
                  </td>
                  <td className="py-3 px-4 text-right">{fmtMoney(row.revenue, currency)}</td>
                  <td className="py-3 px-4 text-right">
                    <div className={`font-medium ${row.roas >= 1 ? 'text-green-600' : 'text-red-600'}`}>
                      {row.roas.toFixed(2)}x
                    </div>
                    <ChangeTag change={row.roas_change} />
                  </td>
                  <td className="py-3 px-4 text-right">
                    <div>{row.cr.toFixed(2)}%</div>
                    <ChangeTag change={row.cr_change} />
                  </td>
                  <td className="py-3 px-4 text-right">
                    <div>{row.aov ? fmtMoney(Math.round(row.aov), currency) : '--'}</div>
                    <ChangeTag change={row.aov_change} />
                  </td>
                  <td className="py-3 px-4 text-right">
                    <div>{row.cpc ? fmtMoney(Math.round(row.cpc), currency) : '--'}</div>
                    <ChangeTag change={row.cpc_change} inverseColor />
                  </td>
                  <td className="py-3 px-4 text-right">
                    <div>{row.conversions}</div>
                    <ChangeTag change={row.conversions_change} />
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export default function CountryDashboard() {
  return (
    <Suspense fallback={null}>
      <CountryDashboardInner />
    </Suspense>
  )
}

function CountryComparisonTable({ rows, currency }: { rows: CountryKpi[]; currency: string }) {
  const { sorted, sortBy, sortDir, toggleSort } = useSortableRows<CountryKpi>(rows)
  return (
    <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
      <div className="px-6 py-4 border-b">
        <h2 className="text-sm font-semibold text-gray-700">Country Comparison</h2>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-100">
              <SortableTh<CountryKpi> col="country" label="Country" align="left" sortBy={sortBy} sortDir={sortDir} onToggle={toggleSort} />
              <SortableTh<CountryKpi> col="total_spend" label={`Spend (${currency})`} sortBy={sortBy} sortDir={sortDir} onToggle={toggleSort} />
              <SortableTh<CountryKpi> col="total_revenue" label={`Revenue (${currency})`} sortBy={sortBy} sortDir={sortDir} onToggle={toggleSort} />
              <SortableTh<CountryKpi> col="roas" label="ROAS" sortBy={sortBy} sortDir={sortDir} onToggle={toggleSort} />
              <SortableTh<CountryKpi> col="ctr" label="CTR" sortBy={sortBy} sortDir={sortDir} onToggle={toggleSort} />
              <SortableTh<CountryKpi> col="cpa" label={`CPA (${currency})`} sortBy={sortBy} sortDir={sortDir} onToggle={toggleSort} />
              <SortableTh<CountryKpi> col="conversions" label="Conversions" sortBy={sortBy} sortDir={sortDir} onToggle={toggleSort} />
            </tr>
          </thead>
          <tbody>
            {sorted.map((row) => (
              <tr key={row.country_code} className="border-b border-gray-50 hover:bg-gray-50">
                <td className="py-3 px-4">
                  <span className="font-medium text-gray-900">{row.country}</span>
                  <span className="text-xs text-gray-400 ml-1">({row.country_code})</span>
                </td>
                <td className="py-3 px-4 text-right">
                  <div>{fmtMoney(row.total_spend, currency)}</div>
                  <ChangeTag change={row.spend_change} inverseColor />
                </td>
                <td className="py-3 px-4 text-right">{fmtMoney(row.total_revenue, currency)}</td>
                <td className="py-3 px-4 text-right">
                  <div className={`font-medium ${row.roas >= 1 ? 'text-green-600' : 'text-red-600'}`}>{row.roas.toFixed(2)}x</div>
                  <ChangeTag change={row.roas_change} />
                </td>
                <td className="py-3 px-4 text-right">{row.ctr.toFixed(1)}%</td>
                <td className="py-3 px-4 text-right">{fmtMoney(Math.round(row.cpa), currency)}</td>
                <td className="py-3 px-4 text-right">
                  <div>{row.conversions}</div>
                  <ChangeTag change={row.conversions_change} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
