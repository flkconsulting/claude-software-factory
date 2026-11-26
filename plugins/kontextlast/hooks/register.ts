import type { Register } from 'claude-code'

// Same defaults as hooks/sf_config.py of software-factory.
const DEFAULT_THRESHOLDS: [number, number] = [150_000, 300_000]

const kTokens = (n: number) => `${Math.round(n / 1000)}k`

// The status line text: load, threshold reached, distance to the next one.
export const line = (tokens: number | undefined, [s1, s2]: [number, number]): string => {
  if (tokens === undefined) return 'Kontext: –'
  const stage = tokens >= s2 ? 2 : tokens >= s1 ? 1 : 0
  if (stage === 2) return `⚠ Kontext ${kTokens(tokens)} · Schwelle 2: neue Sitzung`
  const next = stage === 1 ? s2 : s1
  const mark = stage === 1 ? '⚠ ' : ''
  const reached = stage === 1 ? ' · Schwelle 1' : ''
  return `${mark}Kontext ${kTokens(tokens)}${reached} · bis ${stage + 1}: ${kTokens(next - tokens)}`
}

export const register: Register = on => {
  let thresholds = DEFAULT_THRESHOLDS

  on('session.start', async ($, e, next) => {
    try {
      const home = await $.env.get('HOME')
      const cfg = JSON.parse(await $.fs.read(`${home}/.claude/software-factory.json`))
      const t = cfg?.context_thresholds
      if (Array.isArray(t) && t.length === 2 && t.every(v => Number.isInteger(v) && v > 0) && t[0] < t[1])
        thresholds = [t[0], t[1]]
    } catch {
      // No or unreadable config: keep the defaults, like sf_config.py.
    }
    $.ui.status(line((await $.session.usage()).context.tokens, thresholds))
    return next(e)
  })

  on('session.measure', ($, e, next) => {
    if (e.changed.includes('context')) $.ui.status(line(e.context.tokens, thresholds))
    return next(e)
  })
}
