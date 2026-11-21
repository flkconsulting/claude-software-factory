# software-factory

A transferable way of working with Claude Code, packaged as a plugin: guard hooks for the model choice of helper agents and for the context load of long sessions, rule and project templates, five skills for delegating work, shipping releases, running retrospectives, checking evidence before planning (`pre-check`) and keeping an error index (`error-index`), and a guided setup command for new projects.

This is **Stage 1**: everything runs on one machine, with subagents and git worktrees (variant A). Server-based steering (variant B) is Stage 2 and not yet available.

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

If the official marketplace is not available in your installation, add it first with `/plugin marketplace add anthropics/claude-plugins-official`.

## Set up a project

Run the setup command inside the project you want to equip (namespaced form: `/software-factory:setup-workflow`):

```text
/setup-workflow
```

It asks one question at a time, detects project facts from the repository, and shows every file (or diff) before writing it. It never overwrites silently and never writes to `~/.claude/` without your explicit consent. It produces:

- `AGENTS.md` and `CLAUDE.md` for the project, and an optional `planning/` folder (including the empty error index `planning/ERRORS.jsonl`);
- a proposal for `~/.claude/CLAUDE.md` and `~/.claude/rules/`;
- the per-user settings file `~/.claude/software-factory.json`.

## What is in the box

| Building block | What it does | Where |
| --- | --- | --- |
| Model-choice hook | Rejects (block) or warns about helper-agent dispatches that do not name a model | `hooks/model_choice.py` |
| Context-load hook | Reports once per threshold when a session history gets large and asks for a handover | `hooks/context_load.py` |
| `/setup-workflow` | Guided installation of rules, settings and project templates | `commands/setup-workflow.md` |
| Skill `delegate-work` | Start file, limits, model choice, worktree, report format for delegated work | `skills/delegate-work/` |
| Skill `ship-release` | Release checklist with backup, way back and acceptance list | `skills/ship-release/` |
| Skill `workflow-retrospective` | Key figures and at most three evidenced improvements | `skills/workflow-retrospective/` |
| Skill `pre-check` | Five evidence questions before a plan or implementation, no scoring | `skills/pre-check/` |
| Skill `error-index` | Searchable per-project list of solved error causes with a small script | `skills/error-index/` |
| Templates | Global and project instructions, planning folder, rules (model choice, session handover, briefing, final report, structured questions) | `templates/` |
| Secret scan helpers | Pre-push hook and a blocklist check for this repository's own contributors | `scripts/` |

## Settings

Per-user settings live in `~/.claude/software-factory.json`; hook state in `~/.claude/software-factory/state/`.

```json
{
  "mode": "block",
  "context_thresholds": [150000, 300000]
}
```

- `mode`: `block` (default) enforces the rules; `warn` only shows hints.
- `context_thresholds`: two increasing token counts. The first asks for a handover at the next natural break, the second asks for one immediately.

An unreadable or invalid file falls back to the defaults; a hook never fails with an error.

## Documentation

The `docs/` folder explains where the method comes from and how to apply it:

1. [Development in seven stages](docs/01-development-in-seven-stages.md)
2. [Lessons learned](docs/02-lessons-learned.md)
3. [The working method](docs/03-working-method.md)
4. [Transferring the method](docs/04-transferring-the-method.md)

## Development

Requirements: Python 3.10 or newer; the hooks use only the standard library.

```text
uvx --python 3.10 pytest -q
git config core.hooksPath scripts/git-hooks   # maintainers only: pre-push secret scan
```

The pre-push hook is meant for maintainers: it needs `gitleaks` and a private blocklist (`.blocklist` or `SF_BLOCKLIST_FILE`). Contributors can skip it; CI scans every pull request for secrets, and runs the blocklist check for maintainer pushes and branches of this repository.

## License

Code: MIT, see `LICENSE`. Documentation in `docs/`: CC BY 4.0, see `LICENSE-docs`.

Author: FLK Consulting UG.
