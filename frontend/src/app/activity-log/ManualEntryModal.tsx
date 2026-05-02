'use client'

import { useEffect, useMemo, useState } from 'react'
import { X } from 'lucide-react'
import { apiFetch } from '@/lib/api'

type Branch = { name: string; currency: string }
type CountryOption = { code: string; name: string; adset_count?: number }

const MANUAL_CATEGORIES = [
  { value: 'landing_page', label: 'Landing Page change' },
  { value: 'external_seasonality', label: 'Seasonality / holidays' },
  { value: 'external_competitor', label: 'Competitor activity' },
  { value: 'external_algorithm', label: 'Platform algorithm' },
  { value: 'tracking_integrity', label: 'Tracking / attribution' },
  { value: 'ad_mutation', label: 'Ad change (logged manually)' },
  { value: 'ad_creation', label: 'New ad (logged manually)' },
  { value: 'other', label: 'Other' },
]

type ManualEntryModalProps = {
  open: boolean
  onClose: () => void
  onCreated: () => void
  defaultCountry: string | null
  defaultBranch: string | null
  branches: Branch[]
  countries: CountryOption[]
}

type CampaignOption = { id: string; name: string; platform: string; country?: string | null }

export default function ManualEntryModal({
  open,
  onClose,
  onCreated,
  defaultCountry,
  defaultBranch,
  branches,
  countries,
}: ManualEntryModalProps) {
  const [category, setCategory] = useState('landing_page')
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [occurredAt, setOccurredAt] = useState(() => new Date().toISOString().slice(0, 16))
  const [country, setCountry] = useState(defaultCountry || '')
  const [branch, setBranch] = useState(defaultBranch || '')
  const [platform, setPlatform] = useState('')
  const [sourceUrl, setSourceUrl] = useState('')
  const [captureBaseline, setCaptureBaseline] = useState(true)

  // Optional entity scope — start with campaign picker only. Expanding to adset/ad
  // is left for a follow-up.
  const [campaignId, setCampaignId] = useState('')
  const [campaignQuery, setCampaignQuery] = useState('')
  const [campaignOptions, setCampaignOptions] = useState<CampaignOption[]>([])
  const [campaignLoading, setCampaignLoading] = useState(false)

  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!open) return
    setCategory('landing_page')
    setTitle('')
    setDescription('')
    setOccurredAt(new Date().toISOString().slice(0, 16))
    setCountry(defaultCountry || '')
    setBranch(defaultBranch || '')
    setPlatform('')
    setSourceUrl('')
    setCaptureBaseline(true)
    setCampaignId('')
    setCampaignQuery('')
    setCampaignOptions([])
    setError(null)
  }, [open, defaultCountry, defaultBranch])

  // Campaign autocomplete — debounced search once user types >= 2 chars.
  useEffect(() => {
    if (!open) return
    if (campaignQuery.length < 2) {
      setCampaignOptions([])
      return
    }
    const t = setTimeout(async () => {
      setCampaignLoading(true)
      try {
        const params = new URLSearchParams({ q: campaignQuery, limit: '10' })
        if (branch) params.set('branches', branch)
        const res = await apiFetch<{ items: CampaignOption[] } | CampaignOption[]>(`/api/campaigns/search?${params.toString()}`)
        const items = Array.isArray(res.data) ? res.data : res.data?.items || []
        setCampaignOptions(items)
      } catch {
        setCampaignOptions([])
      } finally {
        setCampaignLoading(false)
      }
    }, 300)
    return () => clearTimeout(t)
  }, [campaignQuery, branch, open])

  // Auto-resolve country from selected campaign.
  useEffect(() => {
    if (!campaignId) return
    apiFetch<{ country: string | null; branch: string | null; platform: string | null }>(
      '/api/changelog/resolve-context',
      { method: 'POST', body: JSON.stringify({ campaign_id: campaignId }) },
    )
      .then((res) => {
        if (!res.success || !res.data) return
        if (!country && res.data.country) setCountry(res.data.country)
        if (!branch && res.data.branch) setBranch(res.data.branch)
        if (!platform && res.data.platform) setPlatform(res.data.platform)
      })
      .catch(() => {})
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [campaignId])

  const canSubmit = useMemo(() => title.trim().length > 0 && !submitting, [title, submitting])

  const handleSubmit = async () => {
    setError(null)
    if (!canSubmit) return
    setSubmitting(true)
    try {
      const body = {
        category,
        title: title.trim(),
        description: description.trim() || null,
        occurred_at: new Date(occurredAt).toISOString(),
        country: country || null,
        branch: branch || null,
        platform: platform || null,
        campaign_id: campaignId || null,
        source_url: sourceUrl.trim() || null,
        capture_baseline: captureBaseline,
      }
      const res = await apiFetch<unknown>('/api/changelog/manual', {
        method: 'POST',
        body: JSON.stringify(body),
      })
      if (!res.success) {
        setError(res.error || 'Failed to create entry')
        return
      }
      onCreated()
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Network error')
    } finally {
      setSubmitting(false)
    }
  }

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/40 pt-12 px-4 overflow-y-auto">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-xl border border-gray-200">
        <div className="flex items-center justify-between px-6 py-4 border-b">
          <h2 className="text-sm font-semibold text-gray-800">Add manual change log entry</h2>
          <button onClick={onClose} className="p-1 hover:bg-gray-100 rounded">
            <X className="w-4 h-4 text-gray-500" />
          </button>
        </div>

        <div className="px-6 py-4 space-y-4">
          {error && (
            <div className="text-xs bg-red-50 border border-red-200 text-red-600 px-3 py-2 rounded">
              {error}
            </div>
          )}

          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Category</label>
            <select
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              {MANUAL_CATEGORIES.map((c) => (
                <option key={c.value} value={c.value}>{c.label}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">
              Title <span className="text-red-400">*</span>
            </label>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. Swapped LP hero image to new angle"
              maxLength={200}
              className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Description</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
              className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Occurred at</label>
              <input
                type="datetime-local"
                value={occurredAt}
                onChange={(e) => setOccurredAt(e.target.value)}
                className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Platform</label>
              <select
                value={platform}
                onChange={(e) => setPlatform(e.target.value)}
                className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm"
              >
                <option value="">None / Mixed</option>
                <option value="meta">Meta</option>
                <option value="google">Google</option>
                <option value="tiktok">TikTok</option>
                <option value="landing">Landing Page</option>
              </select>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Country</label>
              <select
                value={country}
                onChange={(e) => setCountry(e.target.value)}
                className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm"
              >
                <option value="">-- Select --</option>
                {countries.map((c) => (
                  <option key={c.code} value={c.code}>{c.name}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Branch</label>
              <select
                value={branch}
                onChange={(e) => setBranch(e.target.value)}
                className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm"
              >
                <option value="">-- Select --</option>
                {branches.map((b) => (
                  <option key={b.name} value={b.name}>{b.name}</option>
                ))}
              </select>
            </div>
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">
              Campaign (optional — enables baseline capture)
            </label>
            <input
              type="text"
              value={campaignQuery}
              onChange={(e) => { setCampaignQuery(e.target.value); setCampaignId('') }}
              placeholder="Type to search campaigns..."
              className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm"
            />
            {campaignLoading && <div className="text-xs text-gray-400 mt-1">Searching…</div>}
            {!campaignLoading && campaignOptions.length > 0 && !campaignId && (
              <ul className="mt-1 border border-gray-200 rounded-lg bg-white max-h-40 overflow-y-auto">
                {campaignOptions.map((c) => (
                  <li
                    key={c.id}
                    onClick={() => {
                      setCampaignId(c.id)
                      setCampaignQuery(c.name)
                    }}
                    className="px-3 py-2 text-sm hover:bg-gray-50 cursor-pointer"
                  >
                    <div className="font-medium text-gray-800">{c.name}</div>
                    <div className="text-xs text-gray-500">{c.platform}{c.country ? ` · ${c.country}` : ''}</div>
                  </li>
                ))}
              </ul>
            )}
            {campaignId && (
              <div className="text-xs text-emerald-600 mt-1">✓ Campaign linked</div>
            )}
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Source URL (optional)</label>
            <input
              type="url"
              value={sourceUrl}
              onChange={(e) => setSourceUrl(e.target.value)}
              placeholder="https://..."
              className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm"
            />
          </div>

          <label className="flex items-center gap-2 text-sm text-gray-700">
            <input
              type="checkbox"
              checked={captureBaseline}
              onChange={(e) => setCaptureBaseline(e.target.checked)}
              className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
              disabled={!campaignId}
            />
            <span>Capture 7d KPI baseline{!campaignId && ' (requires a linked campaign)'}</span>
          </label>
        </div>

        <div className="px-6 py-3 border-t bg-gray-50 flex justify-end gap-2 rounded-b-xl">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm text-gray-600 hover:bg-gray-100 rounded-lg"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={!canSubmit}
            className="px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
          >
            {submitting ? 'Saving…' : 'Save entry'}
          </button>
        </div>
      </div>
    </div>
  )
}
