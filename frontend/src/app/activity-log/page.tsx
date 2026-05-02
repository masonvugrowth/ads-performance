'use client'

import { useEffect, useState, useRef, useMemo, Suspense } from 'react'
import { useSearchParams } from 'next/navigation'
import { apiFetch } from '@/lib/api'
import { getDateRange, DATE_PRESETS } from '@/components/dashboard/dashboardUtils'
import ActivityLogPanel from './ActivityLogPanel'
import ManualEntryModal from './ManualEntryModal'

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000'

type CountryOption = { code: string; name: string; adset_count: number }
type Branch = { name: string; currency: string }

function ActivityLogInner() {
  const search = useSearchParams()
  const initialBranches = (search.get('branches') || '').split(',').map(s => s.trim()).filter(Boolean)
  const initialCountry = (search.get('country') || '').toUpperCase()
  const initialPlatform = (search.get('platform') || '').toLowerCase()
  const initialRange = search.get('range') || '7d'

  const [country, setCountry] = useState(initialCountry)
  const [platform, setPlatform] = useState(initialPlatform)
  const [selectedBranches, setSelectedBranches] = useState<string[]>(initialBranches)
  const [datePreset, setDatePreset] = useState(initialRange)
  const [customFrom, setCustomFrom] = useState('')
  const [customTo, setCustomTo] = useState('')
  const [branchDropdownOpen, setBranchDropdownOpen] = useState(false)

  const [branches, setBranches] = useState<Branch[]>([])
  const [countries, setCountries] = useState<CountryOption[]>([])
  const [canEditAnalytics, setCanEditAnalytics] = useState(false)
  const [manualModalOpen, setManualModalOpen] = useState(false)
  const [refreshKey, setRefreshKey] = useState(0)

  useEffect(() => {
    apiFetch<{ is_admin: boolean; permissions?: Array<{ section: string; level: string }> }>('/api/auth/me')
      .then((res) => {
        if (!res.success || !res.data) return
        if (res.data.is_admin) { setCanEditAnalytics(true); return }
        const hasEdit = (res.data.permissions || []).some(p => p.section === 'analytics' && p.level === 'edit')
        setCanEditAnalytics(hasEdit)
      })
      .catch(() => {})
  }, [])

  useEffect(() => {
    fetch(`${API_BASE}/api/branches`, { credentials: 'include' })
      .then(r => r.json())
      .then(d => { if (d.success) setBranches(d.data) })
      .catch(() => {})
  }, [])

  const branchParam = selectedBranches.length > 0 ? selectedBranches.join(',') : ''

  useEffect(() => {
    const qp = branchParam ? `?branches=${encodeURIComponent(branchParam)}` : ''
    fetch(`${API_BASE}/api/dashboard/country/countries${qp}`, { credentials: 'include' })
      .then(r => r.json())
      .then(d => { if (d.success) setCountries(d.data) })
      .catch(() => {})
  }, [branchParam])

  const branchDropdownRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (branchDropdownRef.current && !branchDropdownRef.current.contains(e.target as Node)) {
        setBranchDropdownOpen(false)
      }
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [])

  const toggleBranch = (name: string) => {
    setSelectedBranches(prev => prev.includes(name) ? prev.filter(b => b !== name) : [...prev, name])
  }

  const resolvedRange = useMemo(() => {
    if (datePreset === 'custom' && customFrom && customTo) return { from: customFrom, to: customTo }
    return getDateRange(datePreset)
  }, [datePreset, customFrom, customTo])

  const activeCurrency = useMemo(() => {
    if (selectedBranches.length === 0) return 'VND'
    const currencies = [...new Set(selectedBranches.map(b => branches.find(br => br.name === b)?.currency || 'VND'))]
    return currencies.length === 1 ? currencies[0] : 'VND'
  }, [selectedBranches, branches])

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <h1 className="text-2xl font-bold text-blue-600">Activity Log</h1>
        <div className="flex flex-wrap items-center gap-2">
          <select value={datePreset} onChange={e => setDatePreset(e.target.value)}
            className="px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500">
            {DATE_PRESETS.map(p => <option key={p.value} value={p.value}>{p.label}</option>)}
          </select>
          {datePreset === 'custom' && (
            <>
              <input type="date" value={customFrom} onChange={e => setCustomFrom(e.target.value)}
                className="px-2 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
              <span className="text-gray-400">→</span>
              <input type="date" value={customTo} onChange={e => setCustomTo(e.target.value)}
                className="px-2 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
            </>
          )}
          <div className="relative" ref={branchDropdownRef}>
            <button
              onClick={() => setBranchDropdownOpen(o => !o)}
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
              <div className="absolute z-50 mt-1 w-56 bg-white border border-gray-200 rounded-lg shadow-lg py-1 right-0">
                {selectedBranches.length > 0 && (
                  <button
                    onClick={() => setSelectedBranches([])}
                    className="w-full px-3 py-1.5 text-xs text-blue-600 hover:bg-gray-50 text-left"
                  >Clear all</button>
                )}
                {branches.map(b => (
                  <label key={b.name} className="flex items-center gap-2 px-3 py-2 hover:bg-gray-50 cursor-pointer text-sm">
                    <input type="checkbox" checked={selectedBranches.includes(b.name)} onChange={() => toggleBranch(b.name)}
                      className="rounded border-gray-300 text-blue-600 focus:ring-blue-500" />
                    <span>{b.name}</span>
                    <span className="text-gray-400 text-xs ml-auto">{b.currency}</span>
                  </label>
                ))}
              </div>
            )}
          </div>
          <select value={country} onChange={e => setCountry(e.target.value)}
            className="px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500">
            <option value="">All Countries</option>
            {countries.map(c => <option key={c.code} value={c.code}>{c.name}</option>)}
          </select>
          <select value={platform} onChange={e => setPlatform(e.target.value)}
            className="px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500">
            <option value="">All Platforms</option>
            <option value="meta">Meta</option>
            <option value="google">Google</option>
            <option value="tiktok">TikTok</option>
          </select>
        </div>
      </div>

      <ActivityLogPanel
        country={country}
        branches={branchParam}
        platform={platform}
        dateFrom={resolvedRange.from}
        dateTo={resolvedRange.to}
        canEdit={canEditAnalytics}
        onAddManual={() => setManualModalOpen(true)}
        refreshKey={refreshKey}
      />

      {manualModalOpen && (
        <ManualEntryModal
          open={manualModalOpen}
          onClose={() => setManualModalOpen(false)}
          onCreated={() => {
            setRefreshKey(k => k + 1)
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

export default function ActivityLogPage() {
  return (
    <Suspense fallback={<div className="flex items-center justify-center h-64"><div className="text-gray-500">Loading...</div></div>}>
      <ActivityLogInner />
    </Suspense>
  )
}
