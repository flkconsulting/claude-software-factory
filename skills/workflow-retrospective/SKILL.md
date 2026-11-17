---
name: workflow-retrospective
description: Use when the user asks for feedback on the working process, a retrospective or what could be improved, and before designing a new skill or rule for the workflow - collects key figures from git and reports and proposes at most three evidenced improvements, or explicitly none.
---

# Workflow retrospective

The subject is the **process** (who waits, what stalls, what runs twice, where rules are missing, what wastes tokens or compute), not the content of plans. Two goals: less idle time, rework and friction; and the same result for fewer tokens, less Opus and less compute.

**Keep proportion:** "Runs well, no proposals" is a full result and the expected normal case. A proposal is only worth making if its benefit clearly exceeds its cost (implementation, extra rules every session must read, upkeep, friction). Prefer removing a rule to adding one. Collect only figures that are cheap to get.

## 1. Sources (the period under review, usually one day)

- `git log --since=... --stat` and `git log --merges`: commits per task, fix rounds, reverts.
- Report files of delegated work (final-report style reports, see `delegate-work`): first lines (DONE / BLOCKED), open points, deviations from the start file.
- Start files and their follow-ups: many follow-ups mean a gap in the template or skill.
- Questions to the user and their answers: how many, how long open, did work continue meanwhile.
- Session statistics if the user's setup provides them (tokens and model per session); otherwise "not collected".
- Proposals of earlier retrospectives: implemented? effective?

## 2. Key figures (same each time, compare with the previous period)

| Figure | Source |
|---|---|
| Tasks done / blocked | report first lines |
| Commits per task, fix rounds per task | git log, reports |
| Follow-ups and corrections by the user | start files |
| Questions to the user, how many blocking | question files or reports |
| Tokens and model share (Opus share target at most 40 % of helper work) | session statistics, if available |
| Heavy runs repeated after failure | reports |

If a source is missing write "not collected"; propose measuring it only if it would support a real decision. No overall index and no traffic light. Judge cost per task only together with rework: more expensive and right the first time beats cheaper with rework. Never count waiting for the user as inefficiency of the agents.

## 3. What counts as a finding

Every finding needs evidence (file, commit, report). Without evidence, no finding.

- Idle time: a task stood although it could have run.
- Repetition: the same error or follow-up more than once.
- Overlooked: answers or acceptance notes from the user not picked up.
- Unclear ownership: nobody or two parties felt responsible.
- Friction for the user: questions without a recommendation, duplicate questions, things they had to look up.
- Cost: Opus for mechanical work, long start files in every context, agents re-reading the same files, full runs where a focused one sufficed, finished sessions still holding context.

## 4. Report

Short, in the user's language:

```text
# Retrospective <date>

Went well: <one or two sentences>

## Key figures
| Figure | now | previous | trend |

## Proposals (none to at most 3, most important first)
1. <title>
   Goal: working style | cost efficiency
   Observation: <what, with evidence>
   Consequence: <time/risk/cost, estimated>
   Effort: <implementation and running cost of the change>
   Proposal: <concrete change>
   Kind: new skill | change skill | template | rule | tool
   Approval needed: yes/no

## Proposals of earlier periods
- <title>: implemented on ... / effective yes/no / open
```

If all runs well, the report is "Went well", the figures and the sentence "No proposals - the process runs smoothly." Never invent proposals.

## 5. Acting on it

- Changes to existing skills, templates or rules only after the user's answer.
- Never change anything touching approvals, fixed limits or costs without approval.

**Why:** Every new rule costs tokens in every context, so a rule is added only when its benefit clearly exceeds that cost.
