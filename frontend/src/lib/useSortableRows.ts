'use client'

import { useMemo, useState } from 'react'

export type SortDir = 'asc' | 'desc'

export function useSortableRows<T extends Record<string, any>>(
  rows: T[],
  initialSortBy: keyof T | null = null,
  initialDir: SortDir = 'desc'
) {
  const [sortBy, setSortBy] = useState<keyof T | null>(initialSortBy)
  const [sortDir, setSortDir] = useState<SortDir>(initialDir)

  const toggleSort = (col: keyof T) => {
    if (sortBy === col) {
      setSortDir(d => (d === 'desc' ? 'asc' : 'desc'))
    } else {
      setSortBy(col)
      setSortDir('desc')
    }
  }

  const sorted = useMemo(() => {
    if (!sortBy) return rows
    const col = sortBy
    const copy = [...rows]
    copy.sort((a, b) => {
      const av = a[col]
      const bv = b[col]
      if (av == null && bv == null) return 0
      if (av == null) return 1
      if (bv == null) return -1
      if (typeof av === 'number' && typeof bv === 'number') {
        return sortDir === 'asc' ? av - bv : bv - av
      }
      const as = String(av).toLowerCase()
      const bs = String(bv).toLowerCase()
      if (as < bs) return sortDir === 'asc' ? -1 : 1
      if (as > bs) return sortDir === 'asc' ? 1 : -1
      return 0
    })
    return copy
  }, [rows, sortBy, sortDir])

  return { sorted, sortBy, sortDir, toggleSort, setSortBy, setSortDir }
}
