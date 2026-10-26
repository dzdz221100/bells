/** Small shared formatters. Everything renders from data the backend sent. */

const MONTHS = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
]
const DAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']

/** Parse the backend's naive ISO strings without letting the browser shift them. */
export function parseLocal(ts: string): Date | null {
  const m = ts?.match(/^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2}))?/)
  if (!m) return null
  return new Date(+m[1], +m[2] - 1, +m[3], m[4] ? +m[4] : 0, m[5] ? +m[5] : 0)
}

/** HH:MM from a Date, in local time — never via toISOString(), which is UTC. */
export function hhmm(d: Date): string {
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

/** "1 h 40 min" / "45 min" — a duration a traveller can picture. */
export function duration(mins: number): string {
  const h = Math.floor(mins / 60)
  const m = mins % 60
  if (!h) return `${m} min`
  return m ? `${h} h ${m} min` : `${h} h`
}

export function clock(ts: string | null | undefined): string {
  const d = ts ? parseLocal(ts) : null
  if (!d) return '—'
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

export function dayLabel(ts: string | null | undefined): string {
  const d = ts ? parseLocal(ts) : null
  if (!d) return ''
  return `${DAYS[d.getDay()]} ${d.getDate()} ${MONTHS[d.getMonth()]}`
}

export function longDate(ts: string | null | undefined): string {
  const d = ts ? parseLocal(ts) : null
  if (!d) return ''
  return `${d.getDate()} ${MONTHS[d.getMonth()]} ${d.getFullYear()}`
}

export function money(amount: number | null | undefined, currency: string): string {
  if (amount == null) return 'not listed'
  const symbol = currency === 'EUR' ? '€' : currency === 'USD' ? '$' : currency === 'GBP' ? '£' : ''
  const n = Number.isInteger(amount) ? amount : amount.toFixed(2)
  return symbol ? `${symbol}${n}` : `${n} ${currency}`
}

export function daysUntil(dateStr: string): number | null {
  const d = parseLocal(dateStr)
  if (!d) return null
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  d.setHours(0, 0, 0, 0)
  return Math.round((d.getTime() - today.getTime()) / 86_400_000)
}

export const LANGUAGE_NAMES: Record<string, string> = {
  en: 'English', fr: 'Français', es: 'Español', tr: 'Türkçe', de: 'Deutsch',
  it: 'Italiano', pt: 'Português', nl: 'Nederlands',
}

export const languageName = (code: string) => LANGUAGE_NAMES[code] ?? code.toUpperCase()
