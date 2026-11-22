# Start file: <short>

Strand `<short>` of project `<project>`. Keep this file short; reference instead of copy.

**Model:** <haiku|sonnet|opus>

1. **Task:** <one sentence>.
2. **Approval:** <the human's words verbatim and what they approve>. Without a quote there is no approval for merge, push to shared branches, deployment or costs.
3. **Basis:** <concept, plan, earlier reports, project `AGENTS.md` - by path>.
4. **Wait for:** <checkable condition, for example a report file whose first line is `<OTHER> DONE`; delete this part if none>.
5. **Working folder and branch:** worktree `<worktree>` on branch `<branch>`; never work in the main checkout.
6. **Steps:** numbered, each with its check (commands from the project `AGENTS.md`).
7. **Do not:**
   - Push only your own `feature/...` branch, only with green tests, a reviewed diff and a passed secret check. No merge, no push to `main` or shared branches, never force-push.
   - Never read, print or stage secrets.
   - Delete or reset no data store, volume or container you did not create; no paid resources.
   - Type into no other session; approve no permission prompt there.
   - Never use `--dangerously-skip-permissions`.
   - Ask the human only through `sf-status question`, never in the pane.
8. **Report:** file `<state-dir>/reports/<project>/<short>.md`; the first line is exactly `<TOPIC> DONE` or `<TOPIC> BLOCKED`. Then status, evidence (commits, test counts), decisions with reasons, open points, next step, what the human must do. Write this file first and only then send `sf-status report --state done` (or `blocked`); never send it before the file exists, because the supervisor starts follow-up strands from the file.

## Status reporting

- At start, after each step, when waiting and at the end:
  `sf-status report --project <project> --strand <short> --state running|waiting|blocked|done [--progress <0-100>] [--branch <branch>] "<one line>"`
- A question: `sf-status question --project <project> --strand <short> --nr <n> --background "<...>" --recommendation "<...>" "<one sentence>"`, then
  `sf-status report --project <project> --strand <short> --state waiting --waiting-for "human <short>-<n>" "waiting for answer"`.
  Carry on with what does not depend on the answer.
- Heavy runs (full test run, build, end-to-end) only as `<plugin-dir>/scripts/heavy-run.sh <command>`.
- Follow-ups arrive as numbered items at the end of this file; read them when pointed to.
