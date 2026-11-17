# 03 - The working method

**Occasion.** After the build-up, the working method settled into a stable shape: one human decides and accepts, a planning session thinks and plans, workers build, and independent reviewers check. This document describes that shape so it can be applied without re-deriving it.

**Effect.** The method is built around the human as the bottleneck. Everything serves the aim that the human only does what only the human can do: decide, approve, accept. Planning is nearly free; merging, reviewing and the human's attention are scarce.

**Limits.** Stage 1 implements the single-machine form: the planning session itself steers, with subagents per task and a progress log per plan. The supervisor session, the watcher script and the status board are **Stage 2** and are marked below. The method is lean and Kanban-like with release waves; it is not a certified framework.

## Roles

| Role | Who | Task | Must not |
| --- | --- | --- | --- |
| Decider | the human | direction, approvals, answers to questions, acceptance | - |
| Planning | Claude in the chat session | concepts with mock-ups, cross-section, wave plan, publishing outward | change others' things without approval |
| Supervisor (Stage 2) | Claude on a server, loop every 15-30 min | start strands, nudge stalled ones, collect questions, merge, keep the status board | answer questions itself, work outside the wave plan |
| Strand | one Claude session per undertaking, own branch and working folder | write the plan, implement with helper agents, test, report | change foreign areas, merge to the main branch |
| Helper agent | short-lived, per task | implement or review one task | start further agents |
| Watcher (Stage 2) | shell script, every 10 min | report standstill and new reports, nudge the supervisor | - |

## From idea to release

1. **Conversation.** The human describes a problem. Claude asks until the why is clear.
2. **Concept with mock-ups.** Claude writes a concept with clickable drafts; a fresh reviewer reads it as a future developer.
3. **Approval.** The human answers only the questions that lie with them and approves.
4. **Cross-section.** New concepts are checked against the existing ones; shared building blocks are built first.
5. **Wave plan.** What can run in parallel goes into one wave, with ownership per strand (which files, which migration numbers) and a start condition.
6. **Strands.** Each strand writes its own plan and implements it with helper agents. Heavy runs (full test run, end-to-end, build) at most two at a time.
7. **Screenshot acceptance.** Strands with a user interface present their pictures; the human says "fine" or writes on the picture.
8. **Merge.** One wave is merged together, followed by a full test run.
9. **Release.** Build, trial run, backup, roll-out with an acceptance list, only with the human's approval (`skills/ship-release/`).

## Rules that always apply

- Approvals are quoted verbatim in the task; without approval there is no merge to the main branch, no force-push, no roll-out, no cost.
- Secrets are never read, printed or committed.
- Nothing with business content is deleted without a human's confirmation.
- New connections to the outside are security exceptions and go to the human one by one.
- Questions to the human only on real uncertainty, always with the options in words and a recommendation.
- Helper agents: Haiku for mechanical work, Sonnet as the default, Opus for architecture, security and the final review.
- Keep project instructions lean; details live in files that are read only when needed.
- Questions to the human go into a file, never into a choice inside the session's own window; nobody sees those. Work continues on everything else until the answer arrives.
- Keep working instead of waiting: once a start condition is met, the next strand starts in the same pass.
- Finished sessions are closed once the branch is pushed, no test environment is still running and the session is idle; the history stays and can be reopened.
- Work is measured, so its cost can be understood per session and per day.
- A regular retrospective gives at most three evidenced suggestions. "Runs smoothly, no suggestions" is the normal case (`skills/workflow-retrospective/`).

## The status board (Stage 2)

One page for everything the human has to know or do: a morning report, screenshot acceptance, a to-do list with answer fields, approvals with a "done" mark, a tile per strand with its state, what it waits on and its model, and events. The supervisor writes the data, the page refreshes itself. Stage 1 has no such page; the planning session writes state, tasks and approvals into the project's handover file at the end of each phase instead.

## Classification: lean Kanban with release waves, steered by exception

| Building block | Corresponds to | Difference |
| --- | --- | --- |
| Strands in parallel with a cap on strands and on heavy runs | Kanban with a WIP limit | No board by hand; the steering session pulls itself |
| Wave plan with an approval flag, merge per wave | Release-train planning | Waves last hours to days, not weeks |
| Urgent defect past everything else | Kanban expedite lane | - |
| BLOCKED, stall reports, status board | Lean: stop on defects, signal board | The signal is automatic |
| Regular retrospective | Retrospective, kaizen | Frequent, with cost figures; "no change" is explicitly allowed |
| The human approves and accepts, strands decide the rest | Management by exception | The team consists of Claude sessions |
| Trial run, smoke test, roll-out with a way back | DevOps, continuous delivery with test stages | - |
| Project instructions, skills, start files | Process as code | The rules are executable instructions |

**What is new**

1. Planning is nearly free, merging is expensive. Strands write their own plans; what is scarce is merging, review and the human's attention, hence dedicated merge strands.
2. The bottleneck is the human (theory of constraints). Everything serves to let them do only what only they can do: questions as a file with a recommendation, screenshot acceptance, no intermediate states, working on instead of waiting.
3. The cost is tokens, not hours. Cost is measured per finished strand, and the model is chosen per task.

**Where the model is weaker than the established methods**

- Feedback from users comes almost only from the human; iterative methods have a review ritual for this. It becomes important once pilot users exist.
- Merging per wave is one large step and produces conflicts. Smaller waves only once the conflicts noticeably cost.
