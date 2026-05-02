'use client'

import { ArrowUp, ArrowDown, ArrowUpDown } from 'lucide-react'
import { useSortableRows } from '@/lib/useSortableRows'
import { ChangeTag, fmtMoney, FUNNEL_STAGE_PILL } from './dashboardUtils'

export type TaRow = {
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

export default function TaBreakdownTable({
  rows, title, currency,
}: {
  rows: TaRow[]
  title: string
  currency: string
}) {
  const { sorted, sortBy, sortDir, toggleSort } = useSortableRows<TaRow>(rows, 'roas', 'desc')

  const Th = ({ col, label, align = 'right' }: { col: keyof TaRow; label: string; align?: 'left' | 'right' }) => {
    const active = sortBy === col
    return (
      <th
        className={`${align === 'right' ? 'text-right' : 'text-left'} py-3 px-4 text-gray-500 font-medium cursor-pointer select-none hover:text-gray-700`}
        onClick={() => toggleSort(col)}
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

  return (
    <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
      <div className="px-6 py-4 border-b">
        <h2 className="text-sm font-semibold text-gray-700">{title}</h2>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-100">
              <Th col="ta" label="TA" align="left" />
              <Th col="funnel_stage" label="Funnel" align="left" />
              <Th col="spend" label={`Spend (${currency})`} />
              <Th col="revenue" label={`Revenue (${currency})`} />
              <Th col="roas" label="ROAS" />
              <Th col="ctr" label="CTR" />
              <Th col="cpa" label={`CPA (${currency})`} />
              <Th col="conversions" label="Conv" />
            </tr>
          </thead>
          <tbody>
            {sorted.map((row) => (
              <tr key={`${row.ta}-${row.funnel_stage}`}
                className={`border-b border-gray-50 ${row.is_remarketing ? 'bg-amber-50' : 'hover:bg-gray-50'}`}>
                <td className="py-3 px-4 font-medium text-gray-900">{row.ta}</td>
                <td className="py-3 px-4">
                  <span className={`text-xs px-2 py-0.5 rounded-full ${FUNNEL_STAGE_PILL[row.funnel_stage] || FUNNEL_STAGE_PILL.Unknown}`}>
                    {row.funnel_stage}
                  </span>
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
