# 02 - Lessons learned

**Occasion.** During the build-up, a number of things carried the work and a number of things went wrong. Each failure was turned into a rule. This document lists them so the rules in the templates and skills are traceable to an incident rather than to taste.

**Effect.** Most of the speed did not come from more AI but from clear limits, written approvals and reviewers who are not the author. The rules below are the ones that proved themselves; the incident table shows what each rule answers.

**Limits.** These are observations from one team and one kind of project. Items that relate to a separate server (watchers, unattended sessions, a status page) are **Stage 2**; their rules are implemented, see [05 - Server setup](05-server-setup.md).

## What carried the work

- **Approval as a quote.** Every task carries the human's own words verbatim. What is not approved does not happen, not even at night.
- **Limits before permissions.** Fixed prohibitions (no push to the main branch without instruction, no force-push, no secrets, deployment only with approval) made it possible to grant a lot of freedom otherwise.
- **Review first, then show.** A fresh reviewer found three wrong decisions in a cross-section review and eight gaps in a user model before the human invested time.
- **Ask only when it counts.** Strands decide themselves and document the decision. The human is asked only about permissions, privacy, security, cost, irreversible actions or real questions of direction, always with a recommendation.
- **One place for the human.** State, questions, to-dos and approvals on one page instead of scattered through the chat.

## What went wrong, and the lesson

| Moment | What happened | Lesson |
| --- | --- | --- |
| The silent night | Two sessions waited for hours on helper agents that were no longer running. Nobody noticed. | A watcher without AI reports a standstill after 45 minutes. (Stage 2, implemented) |
| The vanished watcher | The script meant to start a release ended without a trace. | Every watcher writes a log line; without one it counts as failed. (Stage 2, implemented) |
| The lost message | A follow-up sent to a session never arrived. | Send text and Enter separately and verify delivery. (Stage 2, implemented) |
| The hasty yes | The human said yes to a preview, then no; the session had already built it. | Withdrawals are normal; the process must tolerate them (git revert, a note with the reason). |
| The wrong suspicion | Claude suspected a doubly used token when logging in again. The measurement showed an expired one. | Establish the cause first, then fix it; never loosen a security rule on suspicion. |
| The license model | A pricing model that grew with usage would have punished exactly the complete use the product promises. | Check the business model and the product promise together. |
| Acceptance after release | Remarks about the interface came after the release and needed a patch release. | Screenshot acceptance before merging. |
| The ambiguous answer | A reply of "No, the costs must be verifiable" allowed two readings. | Put questions with answers in words and a recommendation; ask back on anything ambiguous. |

## What turned out to be expensive

- **Context.** Every helper agent loaded the full project instructions, even for a one-line task. Countermeasure: a lean core, details on demand (see the briefing rule in `templates/rules/briefing.md`).
- **Model.** Helper agents otherwise inherited the strongest model. Countermeasure: a fixed model per kind of task, enforced by a hook (`hooks/model_choice.py`, rule in `templates/rules/model-choice.md`).
- **Long chats.** A very long session loses details to summaries, and every step re-reads the whole history. Countermeasure: start fresh regularly, with a handover as the memory (hook `hooks/context_load.py`, rule in `templates/rules/session-handover.md`).

## Where each lesson lands in this plugin

| Lesson | Where |
| --- | --- |
| Model per task | `hooks/model_choice.py`, `templates/rules/model-choice.md` |
| Long sessions | `hooks/context_load.py`, `templates/rules/session-handover.md` |
| Approval as quote, fixed limits, report format | `skills/delegate-work/` |
| Withdrawals, backup and way back | `skills/ship-release/` |
| Questions with recommendation | `templates/rules/structured-questions.md` |
| Rhythm of improvement | `skills/workflow-retrospective/` |
