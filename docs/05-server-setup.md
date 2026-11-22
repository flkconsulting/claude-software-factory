# 05 - Server setup (variant B)

**Occasion.** Work should keep running while your laptop is closed: long test runs, several strands in parallel, work at night. For that, variant B puts the implementation on a dedicated server. This guide takes you from an empty server to the first wave.

**Effect.** At the end, strands (Claude sessions in tmux) run on the server, a cron job collects their state every three minutes, a status board shows everything in one place, and you answer questions with one command.

**Limits.** Plan about half a day. Nothing here replaces your judgement: the server never approves work by itself (only your quote in the wave plan does), never pushes to `main`, and never installs anything on its own. Read the section "Security limits" before you start.

Placeholders in this guide are written like `<this>`. Replace each one with your own value; nothing here is meant to be copied unchanged. `<ssh-target>` stands for the user and host (or ssh alias) you use to reach the server.

## Prerequisites

- A Linux server (Ubuntu 24.04 LTS recommended), x86 or ARM, at least 4 vCPU and 8 GB RAM.
- A user with `sudo` for the one-time package installation. Normal work runs as a separate user without root (step 1).
- Software on the server: `tmux`, `git`, `flock` (package `util-linux`), `cron`, Python 3.10 or newer, Node (for Claude Code), `gitleaks`.
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

1. As the admin user, install what is missing: `sudo apt install tmux git util-linux cron python3`. Node comes from the official Claude Code installation guide (step 3), not from `apt` by default: the `apt` version of Node on Ubuntu may be older than Claude Code needs. Install `gitleaks` with the method you trust (package manager or the release page of the project).
2. Check each tool as `<work-user>`: `command -v tmux git flock crontab python3 gitleaks`. Every name must print a path.
3. Check the Python version: `python3 --version` must show 3.10 or newer.

## 3. Claude Code login: install and log in yourself

1. Install Claude Code as `<work-user>` following the official installation guide. If the guide needs Node, install the version the official guide requires and check it with `node --version` before you go on.
2. Start `claude` once and log in. **You do this yourself**, in your own session; no script and no agent does it for you, and no login data is ever written into a file of this repository.
3. For a test server or a second server, use a **separate Claude account**. Test runs then do not use up the quota of projects that are running.
4. Leave Claude Code with `/exit` once the login works.

## 4. Get the plugin

1. Pick one way to bring the plugin repository onto the server:
   - Clone it: `git clone <plugin-repo-url> <plugin-dir>`.
   - Or, for a server without access to the repository: on your laptop run `git bundle create <bundle-file> --all` in the plugin repository, copy it with `scp <bundle-file> <ssh-target>:<target-dir>/`, then on the server run `git clone <bundle-file> <plugin-dir>`.
2. Start `claude` in any folder and install the plugin from the marketplace of that clone: `/plugin marketplace add <plugin-dir>`, then `/plugin install software-factory@claude-software-factory`.
3. Restart Claude Code so the hooks take effect.

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
3. Strands push their feature branch there (the pre-push hook still runs). On your laptop you fetch it with `git fetch <ssh-target>:<bare-dir> <branch>` and review it as usual.

## 7. Run `/setup-workflow`, variant B

1. Start `claude` in the project folder on the server and run `/setup-workflow`.
2. Choose variant **B**. The command first does what variant A does (project facts, hooks, planning, project files), then adds the server part.
3. The server part never installs anything. It only checks `tmux`, `crontab` and `flock` and tells you what is missing.
4. It proposes the `server` section of `~/.claude/software-factory.json` as a diff. Set `enabled` to `true` there; `supervisor` stays `false` until you want the supervisor.
5. It proposes `sf-status project add <name> --title <title> --folder <project-folder> ...` and runs it only after you agree.
6. It copies the wave plan template to `planning/wave-plan.md` and the supervisor task to `<state-dir>/supervisor/task.md`.
7. It shows the cron line and the additions for `settings.json`, and writes them only after your explicit consent. Step 8 explains the cron line, the section "Security limits" the permission additions.

## 8. Cron

The cron job is what makes the server work on its own. It starts `sf-status run` every three minutes under `flock`, so two runs never overlap.

1. Open the editor with `crontab -e`.
2. Add the lines of `<plugin-dir>/templates/server/crontab.txt` with `<home>` replaced by the absolute home folder of `<work-user>` (cron does not expand `~` or `$HOME` there). Add every folder from step 5.4 that is not yet on the `PATH` line (for example the folder of `claude`, if it is not `<home>/.local/bin`). Replace `<state-dir>` replaced by your state folder (default `~/.claude/software-factory/server`, spelled out as an absolute path) and `<plugin-dir>` by the plugin folder.
3. Save and check with `crontab -l`.
4. After three minutes look at `<state-dir>/run.log`. A line "server mode disabled" means `server.enabled` is still not `true`.
5. A cron run does not end with an error trace; a problem is one line in `run.log`.

## 9. First wave plan

The wave plan is the only source of approvals. The supervisor starts a strand only for a row whose approval cell begins with `yes`.

1. Open `planning/wave-plan.md` (copied in step 7) and delete the example row.
2. Add one row per strand: short name, title, approval, start condition, branch, migrations, folders that may change.
3. Leave the approval cell at `no` until you decided. To approve, write your own words into the cell: `yes - "<your quote>"`. Without a quote there is no `yes`.
4. Write a start file for the strand with the skill `delegate-work` (it uses `templates/server/strand-start.md`), or let the supervisor do it for an approved row.
5. To start a strand by hand: `sf-status launch --project <name> --short <short> --model <model> --worktree <worktree-dir> --topic <topic>`.
6. For a start at a fixed time with a precondition, use `<plugin-dir>/templates/server/watcher.sh` (see `delegate-work`, section "Watcher").
7. Run full test suites and builds through `<plugin-dir>/scripts/heavy-run.sh <command>`. It lets at most `server.heavy_slots` heavy runs go at once.

## Viewing the state

The state lives in `<state-dir>`. Three views:

- `<state-dir>/STATUS.md` and `<state-dir>/status.html`: the status board with all sections. The HTML file loads nothing from the internet.
- Copy it to your laptop: `scp <ssh-target>:<state-dir>/status.html <local-dir>/`, then open it in your browser.
- Watch a single strand: `ssh <ssh-target>`, then `tmux ls` and `tmux attach -t <project>-<short>`. Leave with `Ctrl-b` then `d`; do not close the session.

Costs shown in the board are a list-price equivalent, not an invoice.

## Answering questions

Strands and the supervisor ask questions only when they are really unsure. Open questions are in the status board with an id.

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
- **Deny list.** `<plugin-dir>/templates/server/settings.json` is a deny list for the work user (push to `main` or `release/*`, force push, `git reset --hard`, `git clean`, forced `rm`). Add its entries to the `settings.json` of the work user. It is a **best-effort** list: patterns can be bypassed by other wording. The real guards are the pre-push hook (step 6) and branch protection on your remote.
- **Approval.** Only your quote in the wave plan approves a strand. The supervisor never invents an approval.
- **Secrets.** Never put secrets into start files, notices, reports or the wave plan. Use the environment or the key store of the work user. Wake triggers and supervisor prompts contain only fixed words and ids, never free text from events.
- **No root.** The work user has no `sudo`. Packages are installed by you, as admin, outside the session.
- **No automatic restart.** A stalled strand is reported exactly once; nothing restarts it for you.
- **Confidential data.** Keep customer data off the server; use test data.
