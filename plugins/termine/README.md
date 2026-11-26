# termine

A Claude Code mod (hooks module in TypeScript) from the `software-factory` marketplace. It shows the next open appointment from the reminders file in the status line under the prompt:

```text
Termin heute 14:00 Kunde X
Termin morgen 09:30 Zahnarzt
Termin Fr 04.12. 14:00 Kunde X
Termin heute Rechnung pruefen
```

The last form is an all-day entry without a time. The status text is German by design (weekdays `Mo Di Mi Do Fr Sa So`, no locale). Only open entries (`[ ]`) within the next 7 days count; a time of day that has passed today and overdue days are skipped. With nothing left, or a missing or unreadable file, the status line is cleared. The file is read again on session start and on every measurement.

## Install

```text
/plugin install termine@claude-software-factory
```

or in the shell: `claude plugin install termine@claude-software-factory`. If the plugin is not found, refresh the marketplace first; when `/plugin marketplace update` does not take effect (seen in the VS Code extension), run `claude plugin marketplace update claude-software-factory` in the shell. Way back: `/plugin uninstall termine@claude-software-factory`. The mod API is early access in Claude Code and may change between releases; the `software-factory` plugin does not depend on it.

## File

The path comes from `reminders_file` in `~/.claude/software-factory.json` (a leading `~/` is resolved against `HOME`), default `~/.claude/reminders.md`; a missing or invalid config keeps the default. Line format, the same as `hooks/reminders.py` reads: `- [ ] YYYY-MM-DD[ HH:MM] | <project> | <text>`. The rule exists twice (Python and TypeScript); `hooks/register.test.ts` holds a table of shared example lines that both test suites check.

## Tests

```text
claude plugin test plugins/termine
pytest tests/test_termine_mod.py
```

The first runs `hooks/register.test.ts`; the second checks manifest, marketplace entry and the shared lines against `reminders.py` (and runs the first where `claude` is installed).
