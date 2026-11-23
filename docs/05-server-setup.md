# 05 - Server setup (variant B)

**Occasion.** Work should keep running while your laptop is closed: long test runs, several strands in parallel, work at night. For that, variant B puts the implementation on a dedicated server. This guide takes you from an empty server to the first wave.

**Effect.** At the end, strands (Claude sessions in tmux) run on the server, a cron job collects their state every three minutes, a status board shows everything in one place, and you answer questions with one command.

**Limits.** Plan about half a day. Nothing here replaces your judgement: the server never approves work by itself (only your quote in the wave plan does), never pushes to `main`, and never installs anything on its own. Read the section "Security limits" before you start.

Placeholders in this guide are written like `<this>`. Replace each one with your own value; nothing here is meant to be copied unchanged. `<ssh-target>` stands for the user and host (or ssh alias) you use to reach the server.

## Prerequisites

- A Linux server (Ubuntu 24.04 LTS recommended), x86 or ARM, at least 4 vCPU and 8 GB RAM.
- A user with `sudo` for the one-time package installation. Normal work runs as a separate user without root (step 1).
- Software on the server: `tmux`, `git`, `flock` (package `util-linux`), `cron`, Python 3.10 or newer, Claude Code, `gitleaks` 8.19 or newer.
- Your own Claude login (step 3). Nobody can do this for you.
- The plugin repository, as a clone or as a `git bundle` file (step 4).
- On your laptop: `ssh` and `scp` access to the server.

If you run the scripts on macOS instead of Linux: `heavy-run.sh` uses `readlink -f`, which needs macOS 12.3 or newer, and `flock` has to be installed first (for example with `brew install util-linux`).

## 1. Create a user without root

1. Log in to the server with your admin access.
2. Create the work user: `sudo adduser <work-user>`.
3. Do not add this user to the `sudo` group.
4. Add your public ssh key to that user's `~/.ssh/authorized_keys`.
5. Log in as `<work-user>` from now on.

## 2. Install the packages

1. As the admin user, install what is missing: `sudo apt install tmux git util-linux cron python3`. Node comes from the official Claude Code installation guide (step 3), not from `apt` by default: the `apt` version of Node on Ubuntu may be older than Claude Code needs. Install `gitleaks` 8.19 or newer with the method you trust. The `apt` package of Ubuntu 24.04 is older (8.16) and lacks the `gitleaks git` command the pre-push hook uses, so every push would fail: take the release archive from the project's release page, check it against the published checksums and put the binary into `/usr/local/bin`.
2. Check each tool as `<work-user>`: `command -v tmux git flock crontab python3 gitleaks`. Every name must print a path. Then `gitleaks git --help` must print the help of that command, not "unknown command".
3. Check the Python version: `python3 --version` must show 3.10 or newer.

## 3. Claude Code login: install and log in yourself

1. Install Claude Code as `<work-user>` following the official installation guide. The native installer puts `claude` into `~/.local/bin` and needs no Node; if you use a method that needs Node, install the version the official guide requires and check it with `node --version` before you go on.
2. Start `claude` once and log in. **You do this yourself**, in your own session; no script and no agent does it for you, and no login data is ever written into a file of this repository.
3. For a test server or a second server, use a **separate Claude account**. Test runs then do not use up the quota of projects that are running.
4. Leave Claude Code with `/exit` once the login works.

## 4. Get the plugin

1. Pick one way to bring the plugin repository onto the server:
   - Clone it: `git clone <plugin-repo-url> <plugin-dir>`.
   - Or, for a server without access to the repository: on your laptop run `git bundle create <bundle-file> --all` in the plugin repository, copy it with `scp <bundle-file> <ssh-target>:<target-dir>/`, then on the server run `git clone <bundle-file> <plugin-dir>`.
2. Install the plugin from the marketplace of that clone, as `<work-user>` in the shell: `claude plugin marketplace add <plugin-dir>`, then `claude plugin install software-factory@claude-software-factory`. Inside a `claude` session the same works with `/plugin marketplace add <plugin-dir>` and `/plugin install software-factory@claude-software-factory`.
3. Install the companion plugin the workflow needs: `claude plugin install superpowers@claude-plugins-official`.
4. Check with `claude plugin list`: both plugins must be listed. Running sessions pick up the hooks only after a restart.

## 5. Put `sf-status` on the PATH

The templates call `sf-status` by its bare name, so it must be found on the `PATH` of your login shell and of cron.

1. Link the script into a folder that is on the `PATH`: `mkdir -p ~/.local/bin` and `ln -s <plugin-dir>/scripts/bin/sf-status ~/.local/bin/sf-status`.
2. Make sure `~/.local/bin` is on the `PATH` (add it to `~/.profile` if not).
3. Test it: `sf-status --help` prints the list of commands.
4. Find the folders of both programs: `command -v claude sf-status`. Cron starts the tmux sessions with its own short `PATH`, and the strands and the supervisor call `claude` and `sf-status` by their bare names. Every folder printed here must be on the `PATH` line of the crontab (step 8). The cron line itself calls `sf-status` by its full path, so it is not affected.

## 6. Secret scan and pre-push hook

`sf-status project add` refuses a repository without a working secret scan.

1. Every project repository needs an executable `pre-push` hook that runs `gitleaks`, in the hooks folder of the repository (`.git/hooks`, or the folder set by `core.hooksPath`). Create the file `pre-push` there with this content:

   ```bash
   #!/usr/bin/env bash
   # Scan the commits about to be pushed with gitleaks; a finding stops the push.
   set -euo pipefail
   null=0000000000000000000000000000000000000000
   root=$(git rev-parse --show-toplevel)
   while read -r _local_ref local_sha _remote_ref remote_sha; do
     [ "$local_sha" = "$null" ] && continue
     if [ "$remote_sha" != "$null" ]; then range="$remote_sha..$local_sha"; else range="$local_sha --not --remotes"; fi
     gitleaks git --redact --no-banner --log-opts="$range" "$root"
   done
   ```

   The hook of the plugin (`<plugin-dir>/scripts/git-hooks/pre-push`) has an extra blocklist check for the plugin maintainers; you do not need it.
2. Make it executable: `chmod +x <hooks-folder>/pre-push`, where `<hooks-folder>` is the hooks folder you chose.
3. Test it with a push to your remote: a clean push goes through, a file with a fake secret is stopped.

### Remotes without GitHub access

If the server may not reach your normal remote, give it a bare repository that you fetch from yourself.

1. On the server: `git init --bare <bare-dir>`.
2. In the project folder: `git remote add <remote-name> <bare-dir>`.
3. Protect the bare remote itself, because it has no branch protection of its own. Run `git -C <bare-dir> config receive.denyNonFastForwards true` and `git -C <bare-dir> config receive.denyDeletes true`. Then create the file `<bare-dir>/hooks/update` with the content below and make it executable (`chmod +x`). It refuses every push to `main` and `release/*` from the server user; you merge on your laptop.

   ```bash
   #!/usr/bin/env bash
   # update hook: refuse changes to protected branches
   case "$1" in
     refs/heads/main|refs/heads/release/*) echo "push to $1 is refused here" >&2; exit 1 ;;
   esac
   ```
4. Strands push their feature branch there (the pre-push hook still runs). On your laptop you fetch it with `git fetch <ssh-target>:<bare-dir> <branch>` and review it as usual.

## 7. Run `/setup-workflow`, variant B

1. Start `claude` in the project folder on the server and run `/setup-workflow`.
2. Choose variant **B**. The command first does what variant A does (project facts, hooks, planning, project files), then adds the server part.
3. The server part never installs anything. It only checks `tmux`, `crontab` and `flock` and tells you what is missing.
4. It proposes the `server` section of `~/.claude/software-factory.json` as a diff. Set `enabled` to `true` there; `supervisor` stays `false` until you want the supervisor (see "Switching the supervisor on").
5. It proposes `sf-status project add <name> --title <title> --folder <project-folder> ...` and runs it only after you agree.
6. It copies the wave plan template to `planning/wave-plan.md` and the supervisor task to `<state-dir>/supervisor/task.md`, with `<state-dir>` filled in.
7. It shows the cron line and the additions for `settings.json`, and writes them only after your explicit consent. Step 8 explains the cron line, the section "Security limits" the permission additions.
8. Check that the state folder is allowed for all sessions of `<work-user>` (the setup command writes it with your consent in the step before; add it by hand if you skipped that). Strands read their start file and write their report in `<state-dir>`, which lies outside their worktree; without this entry each strand stops at the question "Allow this read outside the working directories?", and nobody answers it. Add the absolute path to `~/.claude/settings.json` of `<work-user>`, next to the deny list:

   ```json
   "permissions": { "additionalDirectories": ["<state-dir>"] }
   ```

   Name only `<state-dir>`, not the whole home folder.

## 8. Cron

The cron job is what makes the server work on its own. It starts `sf-status run` every three minutes under `flock`, so two runs never overlap.

1. Open the editor with `crontab -e`.
2. Add the lines of `<plugin-dir>/templates/server/crontab.txt` with `<home>` replaced by the absolute home folder of `<work-user>` (cron does not expand `~` or `$HOME` there). Add every folder from step 5.4 that is not yet on the `PATH` line (for example the folder of `claude`, if it is not `<home>/.local/bin`). Replace `<state-dir>` with your state folder (default `~/.claude/software-factory/server`, spelled out as an absolute path) and `<plugin-dir>` by the plugin folder.
3. Save and check with `crontab -l`.
4. After three minutes look at `<state-dir>/run.log` and `<state-dir>/STATUS.md`. A run that has nothing to report writes nothing to `run.log`: an empty log together with a fresh time stamp in `STATUS.md` (line "Generated") means the job works. A line "server mode disabled" means `server.enabled` is still not `true`.
5. A cron run does not end with an error trace; a problem is one line in `run.log`.

## 9. First wave plan

The wave plan is the only source of approvals. The supervisor starts a strand only for a row whose approval cell begins with `yes`.

1. Open `planning/wave-plan.md` (copied in step 7) and delete the example row.
2. Add one row per strand: short name, title, approval, start condition, branch, base, migrations, folders that may change. `base` is the branch the strand's worktree starts from; leave it empty for the main branch. A strand that builds on another strand's work ("starts when" names its report) names that strand's branch, for example `feature/a`. Wave plans without the `base` column keep working; their worktrees start from the main branch. Adding the column to a plan that already has approved rows changes every row, so the supervisor sees those rows as newly approved once; run `sf-status wake fast-forward` right after the change if that must not happen.
3. Leave the approval cell at `no` until you decided. To approve, write your own words into the cell: `yes - "<your quote>"`. Without a quote there is no `yes`.
4. Write a start file for the strand with the skill `delegate-work` (it uses `templates/server/strand-start.md`), or let the supervisor do it for an approved row.
5. To start a strand by hand: create its worktree first (`git -C <project-folder> worktree add -b <branch> <project-folder>-<short> [<base>]`), then `sf-status launch --project <name> --short <short> --model <model> --worktree <project-folder>-<short> --topic <topic>`. `launch` refuses the project folder itself, so strands never share the main checkout.
   The folder-trust dialog appears the first time you start `claude` in the project folder (step 7); accept it there. In the acceptance run, worktrees created next to the project folder started without the dialog. Right after the first launch still run `tmux attach -t <project>-<short>` once: if the strand waits for any answer, give it by hand and note it.
6. For a start at a fixed time with a precondition, use `<plugin-dir>/templates/server/watcher.sh` (see `delegate-work`, section "Watcher").
7. Run full test suites and builds through `<plugin-dir>/scripts/heavy-run.sh <command>`. It lets at most `server.heavy_slots` heavy runs go at once.

## Switching the supervisor on

Two things must both be on before the supervisor runs: the setting `server.supervisor` and the registration of the project.

1. In `~/.claude/software-factory.json` set `"supervisor": true` in the section `server` (next to `"enabled": true`).
2. There is no `project update`. Remove the project and add it again with the supervisor on and your approval quoted verbatim: `sf-status project remove <name>`, then `sf-status project add <name> --title <title> --folder <project-folder> --supervisor yes --approval-quote "<your quote>"`. The event file of the project stays and the wake offsets continue.
3. While `server.supervisor` was off, triggers kept piling up in `<state-dir>/supervisor/triggers.json`, and approved rows of the wave plan count as new. If old approved rows or old events must not fire, run `sf-status wake fast-forward` before the next cron run: it sets the wake markers to now without raising triggers.
4. Check after the next cron run: `<state-dir>/run.log` shows "supervisor started" and `<state-dir>/supervisor/runs/` gets a file. The file `<state-dir>/supervisor/task.md` must exist (step 7.6) with `<state-dir>` filled in.

## Viewing the state

The state lives in `<state-dir>`. Three views:

- `<state-dir>/STATUS.md` and `<state-dir>/status.html`: the status board with all sections. The HTML file loads nothing from the internet.
- Copy it to your laptop: `scp <ssh-target>:<state-dir>/status.html <local-dir>/`, then open it in your browser.
- Watch a single strand: `ssh <ssh-target>`, then `tmux ls` and `tmux attach -t <project>-<short>`. Leave with `Ctrl-b` then `d`; do not close the session.

Costs shown in the board are a list-price equivalent, not an invoice.

## Answering questions

Strands and the supervisor ask questions only when they are really unsure. Open questions are in the status board with an id, from the next cron run on (the board is written once per run).

1. Read the question, its background and the recommendation.
2. Answer with: `sf-status answer --project <name> --id <question-id> "<your answer>"`.
3. With the supervisor on (`server.supervisor` is `true`), the answer reaches the strand with the next supervisor run. With the supervisor off (the default), nobody passes it on: deliver it yourself with `sf-status deliver --project <name> --strand <short> "<text>"`.
4. An unknown or already answered id is refused with a message; nothing is recorded twice.

## Switching off

You can stop the server layer at any time; variant A and the hooks keep working.

- Pause only the supervisor: create the file `<state-dir>/supervisor/pause`. Delete it to continue.
- Stop everything: set `server.enabled` to `false` in `~/.claude/software-factory.json`. From the next cron run `sf-status run` only writes "server mode disabled" to the log.
- Optional: remove the cron line with `crontab -e`.
- Running strands are not stopped by this. End them with `tmux kill-session -t <project>-<short>` if you want that.

## Security limits

- **Permissions.** Strands and the supervisor run with `claude --permission-mode auto`, with the model named explicitly. Never `--dangerously-skip-permissions`. Permission prompts of other sessions are not approved by any session.
- **Deny list.** `<plugin-dir>/templates/server/settings.json` is a deny list for the work user (push to `main` or `release/*`, force push, `--no-verify` on push and commit, `git reset --hard`, `git clean`, forced `rm`). Add its entries to the `settings.json` of the work user, with `<state-dir>` replaced by the absolute state folder (`sf-status config state_dir`). It is a **best-effort** list: patterns can be bypassed by other wording.
- **What each guard does.** The pre-push hook (step 6) only scans for secrets; it does not stop a push to `main`, and `git push --no-verify` skips it (which is why that flag is on the deny list). What actually stops a push to a protected branch is the protection of the remote: branch protection on GitHub, or the `update` hook of the bare remote (section "Remotes without GitHub access"). Without one of them nothing prevents it.
- **Approval.** Only your quote in the wave plan approves a strand. The supervisor never invents an approval.
- **Secrets.** Never put secrets into start files, notices, reports or the wave plan. Use the environment or the key store of the work user. Wake triggers and supervisor prompts contain only fixed words and ids, never free text from events.
- **No root.** The work user has no `sudo`. Packages are installed by you, as admin, outside the session.
- **No automatic restart.** A stalled strand is reported exactly once; nothing restarts it for you.
- **Confidential data.** Keep customer data off the server; use test data.

## Evidence from the acceptance run

The guide was followed on a fresh server (Ubuntu 24.04, x86, 4 vCPU, 8 GB) with a small sample application for time tracking: two strands on Sonnet, strand B starting after strand A, a question from B to the human, and an artificial stall. Every deviation from this guide was fixed in it. Excerpts, shortened:

Wave plan rows (approval quotes shortened):

```text
| a | Master data ...   | yes - "<quote>" | now                                      | feature/a | ...
| b | Time tracking ... | yes - "<quote>" | after report .../a.md starts with A DONE | feature/b | ...
```

`run.log` after the supervisor was switched on:

```text
<time> supervisor started, 3 triggers open      (approved:a, approved:b, safety)
<time> supervise: ok                            (a launched; b not, "A DONE" missing)
<time> supervisor started, 2 triggers open      (done:a, answer:supervisor-1; b launched)
<time> supervisor started, 1 triggers open      (stall:probe; only noted)
<time> supervisor started, 2 triggers open      (answer:b-1, done:b)
```

Event lines (shortened):

```text
{"kind": "stall", "minutes": 6, "strand": "probe", ...}
{"kind": "question", "id": "b-1", "strand": "b", "question": "When a booking would exceed the remaining budget ...", "recommendation": "Refuse ..."}
{"kind": "answer", "question_id": "b-1", "text": "<human's words>"}
{"kind": "report", "state": "done", "strand": "b", "text": "B DONE: 38 tests green, pushed feature/b"}
```

Report heads:

```text
A DONE
Status: master data implemented, pushed to origin feature/a (secret scan: no leaks).
Evidence: tests/test_master_data.py 17 passed; full suite via heavy-run 18 passed

B DONE
Status: time tracking implemented, pushed to origin feature/b.
Evidence: feature/a brought in via ff-only (the acceptance run predates the `base` column); full suite via heavy-run 38 passed
Decisions: over-budget booking refused, as the human answered question b-1
```

Status board at the end: both strands `done` with their branches, no open questions, the last supervisor runs with their triggers, and usage by model and by project (list-price equivalent).

What the run showed beyond the plan:

- The first strand stopped at a permission question for reading its start file outside the worktree. The stall check reported it exactly once after `stall_minutes`, the supervisor asked the human instead of answering the prompt, and nothing was restarted. The fix is step 7.8 (state folder in `additionalDirectories`).
- Strand B read the answer to its question from the event file itself and finished before the next supervisor run, so the supervisor did not deliver it (correctly: the strand was done). The delivery path `sf-status deliver` is covered by the tests, not by this run.
- Bare remote: a push to `main` was refused by the `update` hook, a clean feature push went through, a file with a fake key was stopped by the pre-push hook.
