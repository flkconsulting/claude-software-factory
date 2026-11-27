---
description: Install the software-factory working rules, hooks settings and project templates into the current project and ~/.claude/
---

# /setup-workflow

You guide the user through setting up the software-factory workflow. Work step by step, one question at a time, and wait for the answer before moving on. Templates live in `${CLAUDE_PLUGIN_ROOT}/templates/` (`CLAUDE.md`, `project-CLAUDE.md`, `AGENTS.md`, `planning/`, `rules/`). Read them directly from that path; do not search for the plugin directory.

General rules for this command:
- Never overwrite an existing file silently. For every file that already exists, show a diff and change it only after the user agrees.
- Never write to `~/.claude/` without showing the content (new file or diff) and getting explicit consent.
- Never print or invent secrets. Do not write credentials into any file.
- Lines starting with `Example:` in the templates are guidance for you; never copy them into a written file - replace them with a project-specific line or drop them.
- Replace every `{{PLACEHOLDER}}` in a template with the confirmed value; no placeholder may remain in a written file.

## Procedure

1. **Variant.** Ask which variant to set up. Offer "A - one machine, subagents and worktrees" and "B - local plus server (stage 2)". Variant B does everything A does and adds the server steps 8 to 12 below (wrap-up is step 13); it needs a prepared server, see `docs/05-server-setup.md` in the plugin repository. If the user is unsure, recommend A and say that B can be added later.

2. **Project facts.** Detect the project name, a one-sentence purpose and the build, test and lint commands from the repository (README, package manifests, Makefile, CI files, scripts). Show what you found and let the user confirm or correct each value. If something cannot be detected, ask.

3. **Hooks: block or warn?** Ask "block or warn?" for the rule hooks (model choice for helper agents, context load).
   - Recommend **block**. Reason: plain hints are overlooked during real work; only a block enforced the rule reliably (helper-agent calls without an explicit model, sessions with a very long history). Warn is available for users who prefer hints only.
   - Write `~/.claude/software-factory.json` with `{"mode": "<block|warn>", "context_thresholds": [150000, 300000]}`. The thresholds are defaults and may be changed in that file. If the file exists, show the diff and ask before changing it.
   - (a) **Reminders file.** The default path is `~/.claude/reminders.md`; the optional key `reminders_file` in `~/.claude/software-factory.json` points elsewhere. If the file is missing, propose creating it with a header line explaining the format (`- [ ] YYYY-MM-DD[ HH:MM] | <project or *> | <text>`; the time is optional, `HH:MM` from 00:00 to 23:59, without a time the entry is all day; `[x]` marks done) and one commented example line (`<!-- - [ ] 2026-01-01 14:00 | * | example reminder -->`). Existing files without times keep working unchanged. Show the content first and ask; the `~/.claude/` rule applies. Never overwrite an existing file.
   - (b) **Notification agent (macOS only).** On macOS, offer a daily macOS notification for due reminders. Get the real interpreter path with `python3 -c 'import sys; print(sys.executable)'` (not a version-manager shim) and check that it is version 3.10 or newer (if not, report it and stop this sub-step). Fill `${CLAUDE_PLUGIN_ROOT}/templates/launchd/reminders.plist` (`{{PYTHON}}` = the `sys.executable` path from above, `{{HOME}}` = home folder; both are detected, not asked) and show the filled plist. Before asking for consent, name every write and command: the two folders `~/.claude/software-factory/bin/` and `~/.claude/software-factory/state/` (created with `mkdir -p`); the copy of `${CLAUDE_PLUGIN_ROOT}/hooks/reminders.py` and `${CLAUDE_PLUGIN_ROOT}/hooks/sf_config.py` into `~/.claude/software-factory/bin/` (a fixed path, because the plugin cache path changes with each version; a rerun refreshes the copy); the file `~/Library/LaunchAgents/software-factory.reminders.plist` (outside `~/.claude`); and the commands `launchctl bootout gui/$(id -u)/software-factory.reminders` (an error is ignored if it was not loaded) and `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/software-factory.reminders.plist`. Do nothing until the user explicitly agrees. After consent: create the folders, copy the two files, write the plist, then run bootout and bootstrap. Name the way back: `launchctl bootout gui/$(id -u)/software-factory.reminders`, delete the plist, and optionally delete `~/.claude/software-factory/bin/` and the log `~/.claude/software-factory/state/reminders-launchd.log`. After installing, suggest one manual run `<python> ~/.claude/software-factory/bin/reminders.py --notify` with a temporary due entry in the reminders file to see a notification; macOS lists osascript notifications under "Script Editor", so if nothing appears, allow notifications for Script Editor in System Settings → Notifications. On any other system say "notification not available on this system; reminders in sessions still work" and change nothing.

4. **Planning location.** Ask where planning documents (roadmap, decisions, questions, findings, TODO) live: a `planning/` folder in this repository (recommended to start with) or a separate repository. For a separate repository, ask for its location and do not create it yourself. Then set `{{PLANNING_PUSH_RULE}}` to the matching variant from the table; never offer a rule that pushes the code repository without asking.

5. **Project files.** Write, from the templates with placeholders filled:
   - `AGENTS.md` (from `${CLAUDE_PLUGIN_ROOT}/templates/AGENTS.md`)
   - `CLAUDE.md` (from `${CLAUDE_PLUGIN_ROOT}/templates/project-CLAUDE.md`)
   - `planning/` (from `${CLAUDE_PLUGIN_ROOT}/templates/planning/`), only if the planning location is this repository. The copy includes `ERRORS.jsonl` (the empty error index, used by the skill `error-index`). If `planning/` already exists, add only the missing files and never overwrite existing ones (the diff rule applies).
   For each file that already exists, show a diff and change it only after consent; otherwise skip it and record it as skipped.
   If the planning location is a separate repository, tell the user that `ERRORS.jsonl` belongs there (path taken from `{{PLANNING_LOCATION}}`) and offer to create the starter file there after asking; the command never creates that repository itself.

6. **Global rules.** Fill `${CLAUDE_PLUGIN_ROOT}/templates/CLAUDE.md` with the confirmed values (see table) and show it, together with `${CLAUDE_PLUGIN_ROOT}/templates/rules/*.md`, as a proposal for `~/.claude/` (`CLAUDE.md` and `rules/`): list new files, and show a diff for files that exist. Write only what the user explicitly approves, file by file.

7. **Companion plugins and tools.** Check what the method relies on and report what is missing; never install anything yourself.
   - Plugins: read `~/.claude/plugins/installed_plugins.json` (if it is missing or unreadable, say so and list all plugins as "not verified"). Required: `superpowers`. Recommended: `context7`, `claude-md-management`, `playwright`.
   - Tools: check with `command -v` for `git`, `gh`, `gitleaks` and `python3` (version 3.10 or newer).
   - For each missing item print one line with its purpose and the install command from the README section "Companion plugins and tools" (plugins: `/plugin install <name>@claude-plugins-official`; tools: the system package manager). Mark required items as required.

8. **Server checks (variant B only).** Check with `command -v` for `tmux`, `crontab` and `flock` and for `sf-status` on the `PATH`. This command never installs anything: for each missing item print one line with its purpose and the install hint from `docs/05-server-setup.md`, and stop here until the required items exist. On macOS, `flock` comes from `util-linux`, and `readlink -f` needs macOS 12.3 or newer.

9. **Server settings (variant B only).** Propose the section `server` of `~/.claude/software-factory.json` as a diff (the general rule for `~/.claude/` applies). Show `"enabled": true` and `"supervisor": false` and name the other defaults (stall 45 minutes, 2 heavy-run slots, 4 strands, state folder `~/.claude/software-factory/server`); change a value only if the user asks.

10. **Register the project (variant B only).** Propose `sf-status project add <name> --title <title> --folder <project-folder>`, with `--main-branch`, `--supervisor` and `--never-touch` as needed, built from the confirmed project facts. Run it only after the user agrees. If it refuses because the pre-push hook with `gitleaks` is missing, report that and let the user fix it; do not write the hook yourself.

    (a) **Release train (variant B only, default off).** Ask whether the project runs a weekly release train; it needs `--supervisor yes`. If the user says yes, show and, after agreement, run `sf-status project set --project <name> --train on --train-day tue --train-time 18:00 --train-tz Europe/Berlin` (change the values only if the user asks). Copy `${CLAUDE_PLUGIN_ROOT}/templates/server/supervisor-train.md` to `<state>/supervisor/train.md` and `${CLAUDE_PLUGIN_ROOT}/templates/server/train-start.md` to `<state>/supervisor/train-start.md`, replacing `<state-dir>`; never overwrite an existing file. `TICKETS.md` and `RELEASES.md` come from step 5. The train strand pushes `release/<version>`: present the push permission for `release/*` as a decision proposal (action, components, risk, way back); never force-push, never `main`. Leave it off if the user declines.

11. **Wave plan and supervisor task (variant B only).** Copy `${CLAUDE_PLUGIN_ROOT}/templates/server/wave-plan.md` to `planning/wave-plan.md` and `${CLAUDE_PLUGIN_ROOT}/templates/server/supervisor-task.md` to `<state>/supervisor/task.md`, where `<state>` is the output of `sf-status config state_dir`. Replace every `<state-dir>` in the copied supervisor task with that output (the supervisor reads the file literally and cannot infer the folder); `<plugin-dir>` placeholders stay as documented for `watcher.sh`. Never overwrite an existing file (diff rule). Leave every approval cell at `no`; approvals are the user's own words and are never written by you.

12. **Cron and permissions (variant B only).** Show, do not write: the cron line from `${CLAUDE_PLUGIN_ROOT}/templates/server/crontab.txt` with the real paths filled in (also `<home>` in its `PATH` line, which must contain the folders printed by `command -v claude sf-status`), and the deny entries and the `additionalDirectories` entry of `${CLAUDE_PLUGIN_ROOT}/templates/server/settings.json` as additions to the `settings.json` of the work user, with `<state-dir>` replaced by the absolute state folder (`sf-status config state_dir`). Say why: strands read their start files and write their reports in that folder, outside the worktree, and without the entry each unattended strand stops at "Allow this read outside the working directories?"; only that folder is listed, not the home folder. Say that the deny list is best effort, that the pre-push hook only scans for secrets (and `--no-verify` is on the deny list for that reason), and that only the remote's protection (GitHub branch protection or the update hook of a bare remote, see `docs/05-server-setup.md`) really stops a push to `main`. Write the crontab or the `settings.json` only after explicit consent for each; never use `--dangerously-skip-permissions`.

13. **Wrap-up.** Print two lists: files written and files skipped (with the reason). Add the list of missing companion plugins and tools from step 7. For variant B add: the registered project, the release train setting (on or off), the files from steps 11 and 12 written or skipped, and the reminder that the cron line only takes effect once it is in the crontab and `server.enabled` is `true`. Name the path of the error index (`ERRORS.jsonl` in the planning location). List the reminders file and the notification agent as written or skipped (with the reason). Remind the user that the hooks take effect in new sessions.

## Placeholders

Ask each question once (`{{PLANNING_PUSH_RULE}}` is not asked; choose the matching variant from step 4); reuse the answer wherever the placeholder appears.

| Placeholder | Question | Default |
| --- | --- | --- |
| `{{USER_NAME}}` | How should Claude call you? | none, required |
| `{{ADDRESS_FORM}}` | Which form of address (for example informal "you" or formal)? | informal |
| `{{REPLY_LANGUAGE}}` | In which language should Claude reply to you? | English |
| `{{PUSH_POLICY}}` | May Claude push? | Default: no push without explicit instruction. Alternative: push the own feature branch when tests are green and the secret scan passed |
| `{{AUTONOMY_LIMITS}}` | Which actions need explicit instruction? (one bullet per action) | edit files outside the repo; change production systems or data, or deploy; wipe or reset databases or storage; create, copy or expose secrets; irreversible git commands, push (except as allowed by the push policy in section 5), delete branches, merge PRs; create or scale paid cloud resources; add dependencies with far-reaching license or security consequences |
| `{{PROJECT_NAME}}` | What is the project called? | detected from the repository |
| `{{PROJECT_PURPOSE}}` | What does the project do, in one or two sentences? | detected from the README |
| `{{BUILD_COMMANDS}}` | Which commands build, test and lint the project? | detected from the repository |
| `{{PLANNING_LOCATION}}` | Where do planning documents live? | `planning/` in this repository |
| `{{PLANNING_PUSH_RULE}}` | derived from the planning location (no question) | Separate planning repository: "Agents commit and push there without asking (pull first)." `planning/` in this repository: "Planning changes are committed with the normal work and follow the push policy." |
