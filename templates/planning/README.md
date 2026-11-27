# Planning

This folder holds the planning, independent of the code branch: what is planned, what was decided, what is open and what we learned. The user and the agents work on it as one team.

## Files

| File | Content |
| --- | --- |
| `DECISIONS.md` | **D-x** decisions confirmed by the user |
| `QUESTIONS.md` | **Q-x** questions to the user, each with a recommendation; section "Present to user" at the top |
| `FINDINGS.md` | **F-x** causes, dead ends, lessons |
| `TICKETS.md` | **T-x** tickets (bugs, ideas, requests) with kind, rank, state and target version |
| `RELEASES.md` | versions (line, state) and which customer gets which version |
| `TODO.md` | next steps, only with references to numbers and plans |
| `ERRORS.jsonl` | one JSON line per solved error cause (date, symptom, cause, fix, ref); search it first, append after the fix (skill `error-index`); no secrets, tokens or names |

## Rules for agents

1. **At start:** read `TODO.md` and the "Present to user" section of `QUESTIONS.md`.
2. **Writing:** {{PLANNING_PUSH_RULE}} Numbers run per kind and are never reused.
3. **D-entries:** agents never write a D-entry themselves; a D-entry is written only on the user's confirmation, with their words and the date.
4. **Q-entries:** questions the agent must not decide alone (security, data protection, money, architecture, irreversible steps, external impact) go to the user as Q-x, each with a recommendation and reason. Answered ones get `-> D-x`.
5. **F-entries:** record causes, dead ends and lessons as F-x.
6. **Decide the rest yourself:** what follows from the repo, docs, tests or a D-x, the agent decides and implements.
7. **Not here:** secrets, credentials, real customer or personal data.
8. **Errors:** on a new error, search ERRORS.jsonl first; after the fix, append one line.
9. **Tickets:** T-x numbers run on and are never reused. Anyone may add a ticket (`new`). Agents never set a ticket beyond `new` on their own: agents never write `assessed`, `planned`, `deferred` or `rejected`; these states are set only on the user's instruction, with their words in the commit or a D-entry. Names only anonymized (customer A), never real ones.

## States

- Q-x: `open` | `answered -> D-x` | `obsolete`
- D-x: valid until a later D-x replaces it (`replaced by D-y`)
