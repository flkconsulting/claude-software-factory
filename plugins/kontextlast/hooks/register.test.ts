import { expect, test } from 'claude-code/testing'

const setup = (on: any, cfg: string | null, tokens?: number) => {
  const seen: (string | undefined)[] = []
  on('env.get', () => ({ value: '/home/x' }))
  on('fs.read', () => (cfg === null ? { deny: 'ENOENT' } : { value: cfg }))
  on('session.usage', () => ({ value: { startedAt: 0, context: { tokens, window: 1_000_000 }, rateLimits: [] } }))
  on('ui.status', (_: unknown, e: { text?: string }) => (seen.push(e.text), { value: undefined }))
  on('session.start', (_: unknown, e: { cwd: string }) => ({ cwd: e.cwd }))
  on('session.measure', (_: unknown, e: { changed: string[] }) => ({ changed: e.changed }))
  return seen
}

const start = ($: any) => $.session.start({ cwd: '/', surface: 'vscode', isInteractive: true })

const measure = ($: any, tokens: number, changed = ['context']) =>
  $.session.measure({ context: { tokens, window: 1_000_000 }, rateLimits: [], changed })

test('below threshold 1 it shows the distance to threshold 1', async ($, on) => {
  const seen = setup(on, '{"context_thresholds":[150000,300000]}', 42_000)
  await start($)
  expect(seen.at(-1)).toBe('Kontext 42k · bis 1: 108k')
})

test('thresholds come from software-factory.json', async ($, on) => {
  const seen = setup(on, '{"context_thresholds":[50000,80000]}', 60_000)
  await start($)
  expect(seen.at(-1)).toBe('⚠ Kontext 60k · Schwelle 1 · bis 2: 20k')
})

test('invalid thresholds fall back to the defaults', async ($, on) => {
  const seen = setup(on, '{"context_thresholds":[300000,150000]}', 160_000)
  await start($)
  expect(seen.at(-1)).toBe('⚠ Kontext 160k · Schwelle 1 · bis 2: 140k')
})

test('missing config keeps the defaults; measure updates the line', async ($, on) => {
  const seen = setup(on, null)
  await start($)
  expect(seen.at(-1)).toBe('Kontext: –')
  await measure($, 310_000)
  expect(seen.at(-1)).toBe('⚠ Kontext 310k · Schwelle 2: neue Sitzung')
})

test('a measurement without a context change leaves the line alone', async ($, on) => {
  const seen = setup(on, null, 42_000)
  await start($)
  const before = seen.length
  await measure($, 999_000, ['cost'])
  expect(seen.length).toBe(before)
})
