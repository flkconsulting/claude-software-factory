# Changelog

All notable changes to this project are documented in this file.

## [0.2.0]

### Added
- Stage 2, variant B (local plus server), additional and switchable off: without a `server` section or with `server.enabled` not `true`, nothing of it acts.
- `sf-status` (`scripts/bin/sf-status`, package `scripts/sf_status/`): append-only event log, project registration with a gitleaks pre-push check, state collector with stall detection (reported once per stall), deterministic `STATUS.md` and escaped, self-contained `status.html`, usage and model report (list-price equivalent, not an invoice), wake triggers and wave plan parser, one cron run, short supervisor run per trigger bundle with retry limit, strand launch in tmux and follow-up delivery, answers to questions.
- `scripts/heavy-run.sh`: heavy-run limiter with `server.heavy_slots` slots.
- `templates/server/`: supervisor task, wave plan, strand start file, watcher script, cron line and a best-effort deny list for `settings.json`.
- Skill `delegate-work`: server mode and watcher.
- `docs/05-server-setup.md`: server setup guide.
- `/setup-workflow` variant B: checks `tmux`, `crontab`, `flock`, proposes the `server` settings, project registration, wave plan, supervisor task, cron line and permission additions (written only after consent).

### Changed
- Plugin and marketplace manifests: version 0.2.0.
- `docs/04` and README describe variant B as available.

## [0.1.0]

Stage 1 (variant A). Entries below were collected under "Unreleased" before.

### Added
- Plugin and marketplace manifests (version 0.1.0).
- Skill pre-check: five evidence questions before planning or implementing, without scoring.
- Skill error-index: per-project JSONL index of solved error causes with a search/append script that rejects obvious secrets; planning template ERRORS.jsonl.
- Documentation (docs/01 to docs/04), README and CI workflow (tests on Python 3.10 and 3.13, secret and blocklist scan).
- README section "Companion plugins and tools" (required: superpowers, git, gh, gitleaks, Python 3.10+; recommended: context7, claude-md-management, playwright) and a check step in `/setup-workflow` that reports missing items without installing them.

### Changed
- Project templates: pointers to pre-check and the error index; definition of done requires every requirement checked off.
