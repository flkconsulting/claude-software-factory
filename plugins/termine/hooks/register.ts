import type { Register } from 'claude-code'

export type Appointment = { day: string; time?: string; project: string; text: string }

// Same rule as LINE and parse() in hooks/reminders.py: only open entries, [0-9] digits.
const LINE =
  /^\s*[-*]\s+\[( |x|X)\]\s+([0-9]{4}-[0-9]{2}-[0-9]{2})(?:\s+([0-9]{2}:[0-9]{2}))?\s*\|\s*([^|]+?)\s*\|\s*(.+?)\s*$/

const WEEKDAYS = ['So', 'Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa']
const DEFAULT_FILE = '~/.claude/reminders.md'
const WINDOW_DAYS = 7

const two = (n: number) => String(n).padStart(2, '0')

// Calendar day number (days since epoch) of a YYYY-MM-DD string, or undefined for a non-date.
const dayNumber = (day: string): number | undefined => {
  const [y, m, d] = day.split('-').map(Number)
  if (y < 1) return undefined
  const t = new Date(Date.UTC(y, m - 1, d))
  t.setUTCFullYear(y)
  if (t.getUTCFullYear() !== y || t.getUTCMonth() !== m - 1 || t.getUTCDate() !== d) return undefined
  return Math.round(t.getTime() / 86_400_000)
}

export const parseLine = (line: string): Appointment | null => {
  const m = LINE.exec(line)
  if (!m || m[1] !== ' ') return null
  if (dayNumber(m[2]) === undefined) return null
  if (m[3] !== undefined) {
    const hh = Number(m[3].slice(0, 2))
    const mm = Number(m[3].slice(3))
    if (hh > 23 || mm > 59) return null
  }
  const a: Appointment = { day: m[2], project: m[4], text: m[5] }
  if (m[3] !== undefined) a.time = m[3]
  return a
}

export const parseAppointments = (text: string): Appointment[] => {
  const out: Appointment[] = []
  for (const line of text.replace(/^\uFEFF/, '').split(/\r?\n/)) {
    const a = parseLine(line)
    if (a) out.push(a)
  }
  return out
}

export const weekday = (d: Date): string => WEEKDAYS[d.getDay()]

export const clip = (text: string, max = 40): string => {
  const chars = Array.from(text)
  return chars.length > max ? `${chars.slice(0, max - 1).join('')}\u2026` : text
}

export const statusText = (items: Appointment[], now: Date): string | undefined => {
  const todayNo = Math.round(Date.UTC(now.getFullYear(), now.getMonth(), now.getDate()) / 86_400_000)
  const nowTime = `${two(now.getHours())}:${two(now.getMinutes())}`
  const open = items
    .map((a, i) => ({ a, i, diff: (dayNumber(a.day) ?? -1) - todayNo }))
    .filter(({ a, diff }) => diff >= 0 && diff <= WINDOW_DAYS && !(diff === 0 && a.time !== undefined && a.time < nowTime))
    .sort(
      (x, y) =>
        x.diff - y.diff ||
        Number(x.a.time !== undefined) - Number(y.a.time !== undefined) ||
        (x.a.time ?? '').localeCompare(y.a.time ?? '') ||
        x.i - y.i,
    )
  const first = open[0]
  if (!first) return undefined
  const { a, diff } = first
  const [y, m, d] = a.day.split('-').map(Number)
  const when = diff === 0 ? 'heute' : diff === 1 ? 'morgen' : `${weekday(new Date(y, m - 1, d))} ${two(d)}.${two(m)}.`
  return ['Termin', when, a.time, clip(a.text)].filter(Boolean).join(' ')
}

const resolvePath = (p: string, home: string): string =>
  p === '~' ? home : p.startsWith('~/') ? `${home}/${p.slice(2)}` : p

// The reminders file named by the config text, or the default when absent or invalid.
export const configuredFile = (cfgText: string): string => {
  try {
    const f = JSON.parse(cfgText)?.reminders_file
    return typeof f === 'string' && f !== '' ? f : DEFAULT_FILE
  } catch {
    return DEFAULT_FILE
  }
}

export const register: Register = on => {
  let file = DEFAULT_FILE

  on('session.start', async ($, e, next) => {
    file = DEFAULT_FILE
    try {
      const home = await $.env.get('HOME')
      try {
        file = configuredFile(await $.fs.read(`${home}/.claude/software-factory.json`))
      } catch {
        // No or unreadable config: default path, like sf_config.py.
      }
      const text = await $.fs.read(resolvePath(file, home))
      $.ui.status(statusText(parseAppointments(text), new Date()))
    } catch {
      $.ui.status(undefined)
    }
    return next(e)
  })

  on('session.measure', async ($, e, next) => {
    try {
      const home = await $.env.get('HOME')
      const text = await $.fs.read(resolvePath(file, home))
      $.ui.status(statusText(parseAppointments(text), new Date()))
    } catch {
      $.ui.status(undefined)
    }
    return next(e)
  })
}
