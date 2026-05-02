'use client'

import { X } from 'lucide-react'

export type FilterChip = {
  key: string
  label: string
  value: string
  onClear: () => void
}

export default function ActiveFiltersChips({
  chips,
  onResetAll,
}: {
  chips: FilterChip[]
  onResetAll: () => void
}) {
  if (chips.length === 0) return null
  return (
    <div className="flex flex-wrap items-center gap-2 mb-4 bg-blue-50/50 border border-blue-100 rounded-lg px-3 py-2">
      <span className="text-[11px] uppercase tracking-wider text-blue-700 font-semibold">
        Active filters
      </span>
      {chips.map((c) => (
        <span
          key={c.key}
          className="inline-flex items-center gap-1 bg-white border border-blue-200 rounded-full px-2 py-0.5 text-xs text-blue-700"
        >
          <span className="text-blue-400">{c.label}:</span>
          <span className="font-medium">{c.value}</span>
          <button
            onClick={c.onClear}
            className="ml-0.5 hover:bg-blue-100 rounded-full p-0.5"
            title={`Clear ${c.label} filter`}
          >
            <X className="w-3 h-3" />
          </button>
        </span>
      ))}
      <button
        onClick={onResetAll}
        className="ml-auto text-xs text-blue-600 hover:text-blue-800 hover:underline"
      >
        Reset all
      </button>
    </div>
  )
}
