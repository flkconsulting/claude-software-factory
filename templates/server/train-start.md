# Start file: release train <version>

Strand `zug-<version with dashes>` of project `<project>`. Keep this file short; reference instead of copy. Fill in only `<version>`, `<date>`, `<line>` and `<train-list>`.

**Model:** sonnet

1. **Task:** release train `<version>` of `<date>`: build the test version of `<version>` and roll it out on the test environment.
2. **Approval:** the words of the wave plan row `zug-<version with dashes>`, verbatim. The quote covers the push of `release/<version>` and the roll-out on the test environment, nothing else: no tag, no push to `main`, no merge, no production.
3. **Basis:** branch `release/<version>` from `<line>`; train list `<train-list>` (tickets and commits); project `AGENTS.md` for commands; `planning/TICKETS.md` and `planning/RELEASES.md` in the main checkout.
4. **Working folder and branch:** worktree `<worktree>` on branch `release/<version>`; never work in the main checkout, except for the entries in `planning/` named below.
5. **Steps** (each with its check from `AGENTS.md`):
   1. Cut off: `release/<version>` from `<line>`, the train list only; leave out everything else.
   2. Build, then the trial run (full tests); stop on red and report.
   3. Backup of the test environment, then roll out `<version>-test.1` only if `AGENTS.md` names a command; otherwise stop and report what is missing.
   4. Acceptance list for the human; set the train tickets to `in-train` and enter the version in `planning/RELEASES.md` of the main checkout (state `testing`).
   5. Ask for the acceptance with `sf-status question`. Collect the findings as tickets (source "acceptance <version>"), never as free text.
   6. Fixes: only on `release/<version>`, built as `-test.N`; a fix round is not a new train. Then the return as a step of its own: bring every fix to `<line>` (cherry-pick or merge as `AGENTS.md` says) and note the evidence. The entry in `planning/RELEASES.md` and any version log kept in the code are never only on `release/`.
   7. Run `sf-status backport --project <project> --version <version>`; it (`git cherry`) must print nothing before the release.
   8. Release only after an acceptance without findings and an empty `backport`: changelog, tickets `shipped`, `planning/RELEASES.md` `released`. Write the commands for tag and push as text for the human; no tag, no push to `main`.
6. **Do not:**
   - Push only `release/<version>`, only with green tests, a reviewed diff and a passed secret check. No merge, no tag, no push to `main` or other shared branches, never force-push.
   - Never read, print or stage secrets.
   - Delete or reset no data store, volume or container you did not create; no paid resources.
   - Type into no other session; approve no permission prompt there.
   - Never use `--dangerously-skip-permissions`.
   - A command marked `local` in `AGENTS.md` is never run on the server; see `strand-start.md`.
   - Ask the human only through `sf-status question`, never in the pane.
7. **Report:** file `<state-dir>/reports/<project>/zug-<version with dashes>.md`; the first line is exactly `RELEASE <version> DONE`, `RELEASE <version> BLOCKED` or `RELEASE <version> IN PROGRESS` (while the acceptance waits), the second `follow-up <n>` (else `-`). Then status, evidence, decisions, open points, what the human must do. Write it before `sf-status report --state done` (or `blocked`).

## Status reporting

- At start, after each step, when waiting and at the end:
  `sf-status report --project <project> --strand zug-<version with dashes> --state running|waiting|blocked|done [--progress <0-100>] [--branch release/<version>] "<one line>"`
- A question: `sf-status question --project <project> --strand zug-<version with dashes> --nr <n> --background "<...>" --recommendation "<...>" "<one sentence>"`, then `sf-status report ... --state waiting --waiting-for "human zug-<version with dashes>-<n>" "waiting for answer"`. The answer arrives as a numbered follow-up at the end of this file.
- Heavy runs only as `<plugin-dir>/scripts/heavy-run.sh <command>`.
