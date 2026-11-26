import { expect, test } from 'claude-code/testing'
import { clip, parseAppointments, parseLine, statusText, weekday } from './register'

// shared-cases:begin
export type SharedCase = {
  line: string
  expect: null | { day: string; time: string | null; project: string; text: string }
}

export const SHARED: SharedCase[] = [
  {"line": "- [ ] 2026-12-05 14:00 | * | Kunde X", "expect": {"day": "2026-12-05", "time": "14:00", "project": "*", "text": "Kunde X"}},
  {"line": "- [ ] 2026-12-10 | * | Rechnung pruefen", "expect": {"day": "2026-12-10", "time": null, "project": "*", "text": "Rechnung pruefen"}},
  {"line": "- [ ] 2026-12-05 00:00 | * | midnight", "expect": {"day": "2026-12-05", "time": "00:00", "project": "*", "text": "midnight"}},
  {"line": "- [ ] 2026-12-05 23:59 | * | late", "expect": {"day": "2026-12-05", "time": "23:59", "project": "*", "text": "late"}},
  {"line": "- [ ] 2026-12-05 24:00 | * | bad hour", "expect": null},
  {"line": "- [ ] 2026-12-05 25:99 | * | bad both", "expect": null},
  {"line": "- [ ] 2026-12-05 9:00 | * | one digit", "expect": null},
  {"line": "- [ ] 2026-12-05 14:60 | * | bad minute", "expect": null},
  {"line": "- [ ] 2026-12-05 14:00:00 | * | seconds", "expect": null},
  {"line": "- [x] 2026-12-05 14:00 | * | done", "expect": null},
  {"line": "- [X] 2026-12-05 14:00 | * | done upper", "expect": null},
  {"line": "* [ ] 2026-12-05 | * | star", "expect": {"day": "2026-12-05", "time": null, "project": "*", "text": "star"}},
  {"line": "  - [ ] 2026-12-05 | proj | indented", "expect": {"day": "2026-12-05", "time": null, "project": "proj", "text": "indented"}},
  {"line": "- [ ] 2026-02-30 | * | bad date", "expect": null},
  {"line": "- [ ] 2028-02-29 | * | leap day", "expect": {"day": "2028-02-29", "time": null, "project": "*", "text": "leap day"}},
  {"line": "- [ ] 2026-12-05|*|tight", "expect": {"day": "2026-12-05", "time": null, "project": "*", "text": "tight"}},
  {"line": "- [ ] 2026-12-05 | * | a | b", "expect": {"day": "2026-12-05", "time": null, "project": "*", "text": "a | b"}},
  {"line": "- [ ] 2026-12-05 | * |", "expect": null},
  {"line": "hello", "expect": null}
]
// shared-cases:end

const NOW = new Date(2026, 11, 5, 14, 30)

const items = (...lines: string[]) => parseAppointments(lines.join('\n'))

test('shared cases parse like the python rule', () => {
  expect(SHARED.length).toBeGreaterThanOrEqual(12)
  for (const c of SHARED) {
    const got = parseLine(c.line)
    const want = c.expect === null ? null : { ...c.expect, time: c.expect.time ?? undefined }
    expect({ line: c.line, got }).toEqual({ line: c.line, got: want })
  }
})

test('parseAppointments strips a BOM and reads CRLF', () => {
  const got = parseAppointments('\uFEFF- [ ] 2026-12-05 | * | a\r\n- [ ] 2026-12-06 | * | b\r\n')
  expect(got.map(a => a.text)).toEqual(['a', 'b'])
})

test('weekday uses getDay without locale', () => {
  expect(weekday(new Date(2026, 11, 6))).toBe('So')
  expect(weekday(new Date(2026, 11, 7))).toBe('Mo')
  expect(weekday(new Date(2026, 11, 12))).toBe('Sa')
})

test('today with time', () => {
  expect(statusText(items('- [ ] 2026-12-05 15:00 | * | Kunde X'), NOW)).toBe('Termin heute 15:00 Kunde X')
})

test('tomorrow', () => {
  expect(statusText(items('- [ ] 2026-12-06 09:30 | * | Zahnarzt'), NOW)).toBe('Termin morgen 09:30 Zahnarzt')
})

test('later day uses weekday and date', () => {
  expect(statusText(items('- [ ] 2026-12-11 14:00 | * | Kunde X'), NOW)).toBe('Termin Fr 11.12. 14:00 Kunde X')
  expect(statusText(items('- [ ] 2026-12-12 14:00 | * | Kunde X'), NOW)).toBe('Termin Sa 12.12. 14:00 Kunde X')
  expect(statusText(items('- [ ] 2026-12-04 14:00 | * | Kunde X'), new Date(2026, 11, 1, 8, 0))).toBe(
    'Termin Fr 04.12. 14:00 Kunde X',
  )
})

test('all day without time', () => {
  expect(statusText(items('- [ ] 2026-12-11 | * | Rechnung'), NOW)).toBe('Termin Fr 11.12. Rechnung')
  expect(statusText(items('- [ ] 2026-12-05 | * | Rechnung'), NOW)).toBe('Termin heute Rechnung')
})

test('past time today is skipped', () => {
  const rest = ['- [ ] 2026-12-05 09:00 | * | vorbei', '- [ ] 2026-12-06 08:00 | * | morgen frueh']
  expect(statusText(items(...rest), NOW)).toBe('Termin morgen 08:00 morgen frueh')
  expect(statusText(items('- [ ] 2026-12-05 14:30 | * | jetzt'), NOW)).toBe('Termin heute 14:30 jetzt')
})

test('all-day today stays next and ranks before timed today', () => {
  const both = ['- [ ] 2026-12-05 15:00 | * | spaeter', '- [ ] 2026-12-05 | * | ganztags']
  expect(statusText(items(...both), NOW)).toBe('Termin heute ganztags')
  expect(statusText(items(...both), new Date(2026, 11, 5, 23, 30))).toBe('Termin heute ganztags')
})

test('overdue is not shown', () => {
  expect(statusText(items('- [ ] 2026-12-01 | * | alt'), NOW)).toBeUndefined()
})

test('beyond seven days is not shown', () => {
  expect(statusText(items('- [ ] 2026-12-12 14:00 | * | x'), NOW)).toBe('Termin Sa 12.12. 14:00 x')
  expect(statusText(items('- [ ] 2026-12-13 14:00 | * | x'), NOW)).toBeUndefined()
})

test('sorted across projects', () => {
  const got = statusText(items('- [ ] 2026-12-09 | b | spaet', '- [ ] 2026-12-07 | a | frueh'), NOW)
  expect(got).toBe('Termin Mo 07.12. frueh')
})

test('same day and time keeps file order', () => {
  expect(statusText(items('- [ ] 2026-12-07 | a | erst', '- [ ] 2026-12-07 | b | zweit'), NOW)).toBe(
    'Termin Mo 07.12. erst',
  )
})

test('no appointments gives undefined', () => {
  expect(statusText([], NOW)).toBeUndefined()
})

test('clip', () => {
  expect(clip('a'.repeat(41))).toBe('a'.repeat(39) + '\u2026')
  expect(clip('a'.repeat(40))).toBe('a'.repeat(40))
  const emoji = clip('\u{1F600}'.repeat(41))
  expect(Array.from(emoji).length).toBe(40)
  expect(emoji).toBe('\u{1F600}'.repeat(39) + '\u2026')
})

test('statusText clips long texts', () => {
  expect(statusText(items(`- [ ] 2026-12-05 | * | ${'a'.repeat(50)}`), NOW)).toBe(`Termin heute ${'a'.repeat(39)}\u2026`)
})

test('calendar days across month and year', () => {
  expect(statusText(items('- [ ] 2027-01-01 08:00 | * | Neujahr'), new Date(2026, 11, 31, 23, 30))).toBe(
    'Termin morgen 08:00 Neujahr',
  )
})

// Exercises the DST path only where the runner's time zone changes on 2027-03-28.
test('calendar days across the DST change', () => {
  const now = new Date(2027, 2, 27, 23, 30)
  expect(statusText(items('- [ ] 2027-03-28 | * | a'), now)).toBe('Termin morgen a')
  expect(statusText(items('- [ ] 2027-03-29 | * | b'), now)).toBe('Termin Mo 29.03. b')
})

// Handler tests

const CONFIG = '/home/x/.claude/software-factory.json'
const DEFAULT_FILE = '/home/x/.claude/reminders.md'

const two = (n: number) => String(n).padStart(2, '0')
const today = () => {
  const d = new Date()
  return `${d.getFullYear()}-${two(d.getMonth() + 1)}-${two(d.getDate())}`
}

const setup = (on: any, files: Record<string, string | undefined>) => {
  const seen: (string | undefined)[] = []
  on('env.get', () => ({ value: '/home/x' }))
  on('fs.read', (_: unknown, e: { path: string }) => {
    const v = files[e.path]
    return v === undefined ? { deny: 'ENOENT' } : { value: v }
  })
  on('ui.status', (_: unknown, e: { text?: string }) => (seen.push(e.text), { value: undefined }))
  on('session.start', (_: unknown, e: { cwd: string }) => ({ cwd: e.cwd }))
  on('session.measure', (_: unknown, e: { changed: string[] }) => ({ changed: e.changed }))
  return seen
}

const start = ($: any) => $.session.start({ cwd: '/', surface: 'vscode', isInteractive: true })
const measure = ($: any) =>
  $.session.measure({ context: { tokens: 1, window: 1_000_000 }, rateLimits: [], changed: ['context'] })

test('session.start reads reminders_file from the config', async ($, on) => {
  const seen = setup(on, {
    [CONFIG]: '{"reminders_file":"~/x/r.md"}',
    '/home/x/x/r.md': `- [ ] ${today()} | * | Kunde X\n`,
  })
  await start($)
  expect(seen.at(-1)).toBe('Termin heute Kunde X')
})

test('reminders_file is used verbatim like sf_config.py (no trimming, empty means default)', async ($, on) => {
  const seen = setup(on, {
    [CONFIG]: '{"reminders_file":"/home/x/sp.md "}',
    '/home/x/sp.md ': `- [ ] ${today()} | * | Leer\n`,
    [DEFAULT_FILE]: `- [ ] ${today()} | * | Standard\n`,
  })
  await start($)
  expect(seen.at(-1)).toBe('Termin heute Leer')
})

test('empty reminders_file falls back to the default path', async ($, on) => {
  const seen = setup(on, { [CONFIG]: '{"reminders_file":""}', [DEFAULT_FILE]: `- [ ] ${today()} | * | Standard\n` })
  await start($)
  expect(seen.at(-1)).toBe('Termin heute Standard')
})

test('missing file is silent', async ($, on) => {
  const seen = setup(on, {})
  await start($)
  expect(seen.at(-1)).toBeUndefined()
  expect(seen.length).toBe(1)
})

test('broken config falls back to the default path', async ($, on) => {
  const seen = setup(on, { [CONFIG]: '{not json', [DEFAULT_FILE]: `- [ ] ${today()} | * | Standard\n` })
  await start($)
  expect(seen.at(-1)).toBe('Termin heute Standard')
})

test('measure re-reads the file', async ($, on) => {
  const files: Record<string, string | undefined> = { [DEFAULT_FILE]: `- [ ] ${today()} | * | eins\n` }
  const seen = setup(on, files)
  await start($)
  expect(seen.at(-1)).toBe('Termin heute eins')
  files[DEFAULT_FILE] = `- [ ] ${today()} | * | zwei\n`
  await measure($)
  expect(seen.at(-1)).toBe('Termin heute zwei')
})

test('an emptied file clears the line', async ($, on) => {
  const files: Record<string, string | undefined> = { [DEFAULT_FILE]: `- [ ] ${today()} | * | eins\n` }
  const seen = setup(on, files)
  await start($)
  files[DEFAULT_FILE] = ''
  await measure($)
  expect(seen.at(-1)).toBeUndefined()
})
