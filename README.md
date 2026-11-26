# software-factory

A transferable way of working with Claude Code, packaged as a plugin: guard hooks for the model choice of helper agents and for the context load of long sessions, rule and project templates, five skills for delegating work, shipping releases, running retrospectives, checking evidence before planning (`pre-check`) and keeping an error index (`error-index`), and a guided setup command for new projects.

Two variants: **A** runs everything on one machine, with subagents and git worktrees (Stage 1). **B** adds a server with tmux strands, a status board and an optional supervisor (Stage 2, additional and switchable off). See [Server](#server).

## Install

```text
/plugin marketplace add flkconsulting/claude-software-factory
/plugin install software-factory@claude-software-factory
```

Restart Claude Code (or start a new session) so the hooks take effect.

The hooks are active in every project as soon as the plugin is enabled, with `mode: block` by default. Agent calls without `model` - also from other plugins - are rejected. To only get hints, create `~/.claude/software-factory.json` with `{"mode": "warn"}`; to stop them, disable the plugin.

## Companion plugins and tools

The working method (concept, then plan, then implementation, with a fresh review before every approval) builds on skills that this plugin does not ship. Install them alongside; `/setup-workflow` checks what is missing and suggests the commands, but never installs anything itself.

| Kind | Name | Why | Install |
| --- | --- | --- | --- |
| Required plugin | `superpowers` | brainstorming, writing-plans, subagent-driven-development, requesting-code-review, verification-before-completion, using-git-worktrees: the concept → plan → implementation chain and the check before approvals | `/plugin install superpowers@claude-plugins-official` |
| Recommended plugin | `context7` | current official library documentation (question 3 of `pre-check`) | `/plugin install context7@claude-plugins-official` |
| Recommended plugin | `claude-md-management` | keeps `CLAUDE.md`/`AGENTS.md` lean and up to date | `/plugin install claude-md-management@claude-plugins-official` |
| Recommended plugin | `playwright` | screenshots for visual acceptance of user interfaces | `/plugin install playwright@claude-plugins-official` |
| Required tool | `git`, `gh`, Python 3.10+ | worktrees, pull requests, hooks | package manager of your system |
| Required tool | `gitleaks` | secret scan before every push | package manager of your system |
| Variant B tools | `tmux`, `cron` (`crontab`), `flock` | strands, the cron run, heavy-run slots | package manager of the server (macOS: `flock` from `util-linux`) |

If the official marketplace is not available in your installation, add it first with `/plugin marketplace add anthropics/claude-plugins-official`.

## Set up a project

Run the setup command inside the project you want to equip (namespaced form: `/software-factory:setup-workflow`):

```text
/setup-workflow
```

It asks one question at a time, detects project facts from the repository, and shows every file (or diff) before writing it. It never overwrites silently and never writes to `~/.claude/` without your explicit consent. It produces:

- `AGENTS.md` and `CLAUDE.md` for the project, and an optional `planning/` folder (including the empty error index `planning/ERRORS.jsonl`);
- a proposal for `~/.claude/CLAUDE.md` and `~/.claude/rules/`;
- the per-user settings file `~/.claude/software-factory.json`;
- on request, the reminders file `~/.claude/reminders.md` and, on macOS, the daily notification agent (see [Reminders](#reminders)).

## Server

Variant B (Stage 2) runs longer work on a dedicated server: strands in tmux, a cron run every three minutes, a status board (`STATUS.md`, `status.html`), an optional supervisor that starts only approved strands, and a limiter for heavy runs. Choose variant B in `/setup-workflow`; it checks `tmux`, `crontab` and `flock`, never installs anything, and writes the cron line and permission additions only after your consent. The server layer is off until `server.enabled` is `true` in `~/.claude/software-factory.json`. Steps that cannot run on the server are announced by a strand and run in your local chat session, woken by `scripts/local-watch.sh` (see "Local steps" in the server setup). Step by step: [Server setup](docs/05-server-setup.md).

## What is in the box

| Building block | What it does | Where |
| --- | --- | --- |
| Model-choice hook | Rejects (block) or warns about helper-agent dispatches that do not name a model | `hooks/model_choice.py` |
| Context-load hook | Reports once per threshold when a session history gets large and asks for a handover | `hooks/context_load.py` |
| Reminders hook | Tells the session about due reminders of its project, once a day; optional daily macOS notification | `hooks/reminders.py` |
| Mod `kontextlast` (separate plugin) | Shows the context load and the distance to the next threshold in the status line | `plugins/kontextlast/` |
| `/setup-workflow` | Guided installation of rules, settings and project templates | `commands/setup-workflow.md` |
| Skill `delegate-work` | Start file, limits, model choice, worktree, report format for delegated work | `skills/delegate-work/` |
| Skill `ship-release` | Release checklist with backup, way back and acceptance list | `skills/ship-release/` |
| Skill `workflow-retrospective` | Key figures and at most three evidenced improvements | `skills/workflow-retrospective/` |
| Skill `pre-check` | Five evidence questions before a plan or implementation, no scoring | `skills/pre-check/` |
| Skill `error-index` | Searchable per-project list of solved error causes with a small script | `skills/error-index/` |
| Templates | Global and project instructions, planning folder, rules (model choice, session handover, briefing, final report, structured questions) | `templates/` |
| `sf-status` | Server state, status board, wake triggers, supervisor run, strand launch and answers (variant B) | `scripts/bin/sf-status`, `scripts/sf_status/` |
| Heavy-run limiter | Runs a heavy command only while one of N slots is free (variant B) | `scripts/heavy-run.sh` |
| Server templates | Supervisor task, wave plan, strand start file, watcher, cron line, deny list (variant B) | `templates/server/` |
| Local-step watcher | Polls the server over ssh and wakes the local chat session when a strand announces a step that must run locally (variant B) | `scripts/local-watch.sh` |
| Secret scan helpers | Pre-push hook and a blocklist check for this repository's own contributors | `scripts/` |

## Settings

Per-user settings live in `~/.claude/software-factory.json`; hook state in `~/.claude/software-factory/state/` (context-load markers, and `reminders-<session>-<date>` markers that are pruned after their day).

```json
{
  "mode": "block",
  "context_thresholds": [150000, 300000],
  "reminders_file": "~/.claude/reminders.md"
}
```

- `mode`: `block` (default) enforces the rules; `warn` only shows hints.
- `context_thresholds`: two increasing token counts. The first asks for a handover at the next natural break, the second asks for one immediately.
- `reminders_file`: path of the reminders file (default `~/.claude/reminders.md`). Give an absolute path or one starting with `~/`; relative paths resolve against the working folder of the process. A missing file means no output. Format: see [Reminders](#reminders).
- `server` (optional, variant B): a section with `enabled` (default `false`) and further settings; see [Server setup](docs/05-server-setup.md). Without it nothing of Stage 2 is active.

An unreadable or invalid file falls back to the defaults; a hook never fails with an error.

## Reminders

A reminder that must outlive a session goes as one line into the reminders file (default `~/.claude/reminders.md`, setting `reminders_file`):

```text
- [ ] 2026-12-04 | my-project | check the acceptance of release train 2
- [ ] 2026-12-01 | * | renew the domain
```

- Format: `- [ ] YYYY-MM-DD | <project or *> | <text>`. `[x]` marks an entry done; lines that do not match are ignored.
- `<project>` is the name of the folder that holds `.git` (case-insensitive); `*` applies to every project.
- The reminders hook reports open entries that are due (the day is today or earlier) at the first prompt of a session, once per session and day. Outside a repository only `*` entries are reported. A missing file means no output.
- `python3 hooks/reminders.py --notify` shows one macOS notification for the due entries of all projects. `/setup-workflow` can install it as a launchd agent (`software-factory.reminders`, daily at 09:07 and at login) after your consent; it copies `reminders.py` and `sf_config.py` to `~/.claude/software-factory/bin/`.
- After a plugin update, rerun the setup step (or copy the two files again) so the copy in `~/.claude/software-factory/bin/` is current.
- Way back for the agent: `launchctl bootout gui/$(id -u)/software-factory.reminders`, then delete `~/Library/LaunchAgents/software-factory.reminders.plist`. Optional cleanup: `~/.claude/software-factory/bin/` and the log `~/.claude/software-factory/state/reminders-launchd.log`.

### Known limitation

If the context-load hook holds back the first prompt of a day (block mode, threshold 2), the reminders shown with that prompt are lost for that session that day; the daily notification still covers them.

## Context load in the status line (mod)

`kontextlast` is a separate plugin in the same marketplace: a Claude Code mod (hooks module in TypeScript) that keeps the session's context load in the status line under the prompt, measured like the context-load hook and against the same `context_thresholds`:

```text
Kontext 94k · bis 1: 56k
⚠ Kontext 160k · Schwelle 1 · bis 2: 140k
⚠ Kontext 310k · Schwelle 2: neue Sitzung
```

Install it next to `software-factory`; the context-load hook keeps its notice and block, the mod only shows the figure:

```text
/plugin install kontextlast@claude-software-factory
```

The mod API is early access in Claude Code and may change between releases; `software-factory` itself does not depend on it. Way back: `/plugin uninstall kontextlast@claude-software-factory`.

## Documentation

The `docs/` folder explains where the method comes from and how to apply it:

1. [Development in seven stages](docs/01-development-in-seven-stages.md)
2. [Lessons learned](docs/02-lessons-learned.md)
3. [The working method](docs/03-working-method.md)
4. [Transferring the method](docs/04-transferring-the-method.md)
5. [Server setup](docs/05-server-setup.md)

## Development

Requirements: Python 3.10 or newer; the hooks use only the standard library.

```text
uvx --python 3.10 pytest -q
claude plugin test plugins/kontextlast          # mod tests; pytest runs them too where claude is installed
git config core.hooksPath scripts/git-hooks   # maintainers only: pre-push secret scan
```

The pre-push hook is meant for maintainers: it needs `gitleaks` and a private blocklist (`.blocklist` or `SF_BLOCKLIST_FILE`). Contributors can skip it; CI scans every pull request for secrets, and runs the blocklist check for maintainer pushes and branches of this repository.

## License

Code: MIT, see `LICENSE`. Documentation in `docs/`: CC BY 4.0, see `LICENSE-docs`.

Author: FLK Consulting UG.
