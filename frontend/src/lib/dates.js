// Daty jako 'YYYY-MM-DD' (bez stref czasowych) – liczone w UTC, żeby uniknąć przesunięć przy zmianie czasu.
const DAY = 86400000

export function parseISO(iso) {
  const [y, m, d] = iso.split('-').map(Number)
  return Date.UTC(y, m - 1, d)
}

export function toISO(ms) {
  return new Date(ms).toISOString().slice(0, 10)
}

export function todayISO() {
  const d = new Date()
  return toISO(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()))
}

export function addDays(iso, n) {
  return toISO(parseISO(iso) + n * DAY)
}

// Dodaje miesiące; przy krótszym miesiącu przycina do ostatniego dnia (31.08 + 2 mies. = 31.10, 31.12 + 2 = 28/29.02).
export function addMonths(iso, n) {
  const [y, m, d] = iso.split('-').map(Number)
  const target = new Date(Date.UTC(y, m - 1 + n, 1))
  const last = new Date(Date.UTC(target.getUTCFullYear(), target.getUTCMonth() + 1, 0)).getUTCDate()
  target.setUTCDate(Math.min(d, last))
  return toISO(target.getTime())
}

// a − b w dniach
export function diffDays(a, b) {
  return Math.round((parseISO(a) - parseISO(b)) / DAY)
}

const DNI = ['nd', 'pn', 'wt', 'śr', 'cz', 'pt', 'sb']

export function formatPL(iso) {
  if (!iso) return '—'
  const [y, m, d] = iso.split('-')
  return `${d}.${m}.${y}`
}

export function weekdayPL(iso) {
  return DNI[new Date(parseISO(iso)).getUTCDay()]
}
