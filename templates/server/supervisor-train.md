# Supervisor: release train

Read only when a trigger `train:<date>` or `answer:train-...` is in the list. The project runs a weekly release train.

## `train:<date>`

The cut-off is reached. Prepare the decision, then ask one question:

- Train list: `sf-status tickets --train <date>` and the `git log` of each line since its last test version.
- Is the full test run green? Which acceptances are missing? What waits, and why? Notes for the human.
- Ask **one question** with `sf-status train question --project <project> --date <date> --background "<...>" --recommendation "<...>" "<text>"`. The text names every candidate version (the first `planned` version of each line), one candidate per line, and says what is on the test environment: a new test version replaces the previous one. Give a recommendation with its reason.
- No candidate: say so in the question and propose a version.

## `answer:train-<...>`

`sf-status` evaluates clear answers itself. You are woken only for an unclear one: ask back with `sf-status train question` and both readings. Never interpret the answer.

## `safety`

Read `sf-status tickets`. A critical bug with state `planned` and the version of a candidate, and no open train question: ask "critical bug T-<n>" with `sf-status train question`.

## Start

When the wave plan has a row `zug-<version with dashes>` with approval `yes` (the standard start rules apply): fill `<state-dir>/supervisor/train-start.md` into `<state-dir>/start/<project>/<short>.md`, replacing only `<version>`, `<date>`, `<line>` and `<train-list>`; the worktree comes from `origin/<line>` on the branch `release/<version>`.

You never write the wave plan: the approval row comes from `sf-status`.
