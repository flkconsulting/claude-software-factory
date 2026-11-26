# Changelog

All notable changes to this project are documented in this file.

## [0.5.0]

### Added
- Mod `kontextlast` 0.1.0 as a separate plugin in the marketplace (`plugins/kontextlast/`): shows the context load and the distance to the next threshold in the status line, thresholds from `context_thresholds`. Tests: `plugins/kontextlast/hooks/register.test.ts` (`claude plugin test`), `tests/test_kontextlast_mod.py`.

## [0.4.1]

### Fixed
- Pre-push hook fails closed when gitleaks reports an error: gitleaks 8.30 exits 0 although its git call failed (`ERR error="stderr is not empty"`), so the push went through unscanned. An `ERR` line in its output now aborts the push (`tests/test_pre_push.py`).

### Changed
- Report rule: `<TOPIC> DONE` only once nothing waits for the user. While an acceptance or decision lies with them the first line stays `<TOPIC> IN PROGRESS`, and the session is not closed (`delegate-work`, `strand-start.md`, `supervisor-task.md`, server guide). Before, a strand reported DONE while waiting for acceptance, its tmux session was closed, and the answer needed a restart.

## [0.4.0]

### Added
- Reminders hook `hooks/reminders.py` (UserPromptSubmit): reports open entries of the reminders file that are due for the project of the session (and `*`), once per session and day; marker files `reminders-<session>-<date>` in the state folder.
- `reminders.py --notify`: one macOS notification for the due entries of all projects.
- Template `templates/launchd/reminders.plist`: launchd agent `software-factory.reminders`, daily at 09:07 and at login.
- `/setup-workflow` step 3: optional reminders file and, on macOS after consent, the notification agent (with the way back).
- After a plugin update, rerun the setup step (or copy `reminders.py` and `sf_config.py` again) so the copy in `~/.claude/software-factory/bin/` is current.
- Setting `reminders_file` (default `~/.claude/reminders.md`); global rule "Reminders across sessions" in `templates/CLAUDE.md`.

### Changed
- Report first line while a session works: `<TOPIC> IN PROGRESS`; a new follow-up sets it back before anything else, the second line names the last follow-up handled (`follow-up <n>`). Before a wait of more than an hour or a long measurement the session writes a checkpoint into its report (`skills/delegate-work`, `templates/server/strand-start.md`, `templates/server/supervisor-task.md`).
- `docs/05-server-setup.md`: lessons from migrating an existing project: seed push as a human step and later base sync by bundle and `git fetch`, `mkdir -p` before `rsync`, narrower `pkill` patterns, free-text answers in `/setup-workflow`, worktree-wide `env` and an untracked wave plan, exactly one local watcher per project, a code generation hint and asking before cleanup deletions, correct wording that the supervisor starts only with an open trigger.
- `docs/05-server-setup.md`: evidence paragraph "Migration of an existing project".
- `templates/server/supervisor-task.md`: the supervisor runs `git fetch origin` in the project folder and creates new worktrees from `origin/<base>` (or `origin/<main branch>`), so a base sync by bundle into the bare remote is enough.
- `docs/05-server-setup.md`: project folder after a base sync, prompt suggestions in strand panes, stopping the old watcher.

### Fixed
- `scripts/local-watch.sh`: `kill` ends the watcher at once, also during its poll interval (the sleep is waited for in the background).

## [0.3.1]

### Fixed
- `sf-status deliver` watches the pane during its wait and accepts the first sighting of the pointer. Before, it looked once after 20 s and reported "did not arrive" (no `delivered` event) when a fast strand had already answered and scrolled the pointer out of view.

### Changed
- `docs/05-server-setup.md`: corrections from a dry run on a fresh server: non-interactive `adduser`, git identity of the work user, bare remote with `--initial-branch=main` and seeding `main` before protecting it, cron section as a check of what `/setup-workflow` wrote (manual `crontab -e` as fallback), `PATH` for the non-interactive ssh shell, closing idle strand sessions.
- `docs/05-server-setup.md`: evidence paragraph "Local steps dry run" (happy path, negative cases, deviations).

## [0.3.0]

### Added
- Local steps: events `local_request` and `local_result`; commands `sf-status local request`, `local pending` and `local result` (a request is refused if the commit is not the head of `origin/<branch>` or the strand already has an open one); trigger `local:<id>` for delivery with the supervisor on.
- Board section "Waiting for local step"; strands waiting for `local <id>` are exempt from the stall check while that request is open; setting `server.local_notice_hours` (default 8) gives one warning notice per request, hidden once a result exists; marker `markers/local.json`.
- `scripts/local-watch.sh`: ssh poller for the local chat session (exit codes 10, 11, 12; per-call ssh timeout).
- Rules for local steps in the strand start, supervisor task, project `AGENTS.md` template and skill `delegate-work`.
- `docs/05-server-setup.md`: section "Local steps".
- `sf-status deliver` reads the follow-up text from stdin when the text is `-` (like `local result`), so free text never passes through the remote shell.

## [0.2.2]

### Changed
- workflow-retrospective: session transcripts as a source, tool-before-text principle, review of always-loaded agent instructions.

## [0.2.1]

### Fixed
- Project entries are checked strictly (types, duplicate names); an invalid entry is refused instead of being read as "supervisor on". `sf-status` without `HOME` prints one line instead of a traceback. The strand id `server` is reserved.
- Finished and blocked strands free their `max_strands` slot, so the supervisor can launch again while their tmux pane is still open.
- Projects and worktrees are stored and compared by their real paths, so symlinked folders map to the right project. Projects registered through a symlinked path before 0.2.1 keep working; re-registering stores the real path.
- The supervisor timeout ends the whole process group of the `claude` run, including children that ignore TERM.
- `heavy-run.sh` forwards TERM and INT to the command (Ctrl-C reaches the command and its children), passes stdin through, and releases the slot only after the command has ended.
- `project add`, `project remove` and `project list` refuse an unreadable or invalid `projects.json` with one `sf-status:` line and exit 1, instead of overwriting or silently ignoring it.
- The status page escapes backslashes and strips C1 and bidirectional control characters.
- Cache writes in the usage report are counted from the `cache_creation` sub-dictionary.

## [0.2.0]

### Added
- Stage 2, variant B (local plus server), additional and switchable off: without a `server` section or with `server.enabled` not `true`, nothing of it acts.
- `sf-status` (`scripts/bin/sf-status`, package `scripts/sf_status/`): append-only event log, project registration with a gitleaks pre-push check, state collector with stall detection (reported once per stall), deterministic `STATUS.md` and escaped, self-contained `status.html`, usage and model report (list-price equivalent, not an invoice), wake triggers and wave plan parser (columns read by the header row; column `base` names the branch a strand's worktree starts from), one cron run, short supervisor run per trigger bundle with retry limit (cron and supervisor change `triggers.json` only under a shared lock), strand launch in tmux and follow-up delivery, answers to questions.
- `scripts/heavy-run.sh`: heavy-run limiter with `server.heavy_slots` slots.
- `templates/server/`: supervisor task, wave plan, strand start file, watcher script, cron line (with `LANG=C.UTF-8`) and a best-effort deny list for `settings.json`.
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
