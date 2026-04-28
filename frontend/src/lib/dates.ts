// Format a Date as YYYY-MM-DD in the browser's LOCAL timezone.
// `.toISOString()` converts to UTC, which in Asia/Ho_Chi_Minh (UTC+7) shifts
// midnight-local back into the previous calendar day — e.g. `new Date(2026, 2, 1)`
// (March 1 local) becomes "2026-02-28" via toISOString. Date-range filters that
// hit the API need the local calendar date, so always go through this helper.
export function formatLocalDate(d: Date): string {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}
