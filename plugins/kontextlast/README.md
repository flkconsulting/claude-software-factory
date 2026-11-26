# kontextlast

A Claude Code mod (hooks module in TypeScript) from the `software-factory` marketplace. It shows the context load of the session in the status line under the prompt, together with the distance to the next threshold:

```text
Kontext 94k · bis 1: 56k
⚠ Kontext 160k · Schwelle 1 · bis 2: 140k
⚠ Kontext 310k · Schwelle 2: neue Sitzung
```

The status text is German by design.

## Install

```text
/plugin install kontextlast@claude-software-factory
```

or in the shell: `claude plugin install kontextlast@claude-software-factory`. If the plugin is not found, refresh the marketplace first; when `/plugin marketplace update` does not take effect (seen in the VS Code extension), run `claude plugin marketplace update claude-software-factory` in the shell. Way back: `/plugin uninstall kontextlast@claude-software-factory`. The mod API is early access in Claude Code and may change between releases; the `software-factory` plugin does not depend on it.

## Thresholds

The two thresholds come from `context_thresholds` in `~/.claude/software-factory.json` (two increasing token counts, default `[150000, 300000]`), the same setting the context-load hook of `software-factory` uses. A missing or invalid file keeps the defaults.

## Tests

```text
claude plugin test plugins/kontextlast
pytest tests/test_kontextlast_mod.py
```

The first runs `hooks/register.test.ts`; the second checks manifest and marketplace entry (and runs the first where `claude` is installed).
