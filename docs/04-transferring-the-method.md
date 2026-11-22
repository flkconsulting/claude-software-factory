# 04 - Transferring the method: single machine or with a server

**Occasion.** The method grew in one project, but it should be usable in the next one without long deliberation. The first decision is where the work runs: purely local, or local plus a dedicated server.

**Effect.** Local is enough as long as the work fits into one session per day and nothing has to run at night. Once longer runs, several parallel strands or work with a closed laptop are needed, a server pays off. A project can start small and local and switch later: the wave plan and the status board stay, only the supervisor moves to the server.

**Limits.** This plugin implements **variant A, purely local** (Stage 1) and **variant B, local plus server** (Stage 2, available from version 0.2.0). Stage 2 is additional and can be switched off; without a `server` section in the settings nothing of it is active. The server setup is in [05 - Server setup](05-server-setup.md).

## Decision aid

| Question | Rather purely local | Rather local plus server |
| --- | --- | --- |
| How long do tests and build take? | minutes | half an hour and more |
| How many undertakings at once? | one, at most two | three or more |
| Should work continue at night? | no | yes |
| How large is the code? | small to medium | large, several parts |
| Is there confidential data that must not leave the machine? | yes - stay local | no, or only test data on the server |
| Who steers? | the chat session itself | a supervisor on the server, the chat for planning |

## Variant A - purely local (Stage 1)

- **Where:** everything on the one machine; one working folder (git worktree) and branch per undertaking.
- **Steering:** the chat session itself, with a subagent per task and a progress log per plan.
- **Overview:** a handover file; the chat session writes state, tasks and approvals into it at the end of each phase.
- **Limits:** works only while the machine is open and the session active; heavy runs one after another.
- **Setup effort:** about an hour.

## Variant B - local plus server (Stage 2)

- **Where:** planning, publishing and everything that needs a login in your own browser; implementation, tests and build on the server.
- **Steering:** a supervisor on the server (Claude in a loop) following the wave plan; a watcher script as a safety net.
- **Overview:** a status board with all sections; a view of individual sessions on the server.
- **Limits:** permission prompts and an exhausted quota stop sessions; new connections to the outside remain exceptions.
- **Setup effort:** about half a day including the server.

## Same in both variants

- Concept before plan, plan before code; a fresh reviewer before every approval.
- Approval as a quote, fixed limits, questions only on real uncertainty.
- Lean project instructions, details on demand, a code map.
- A fixed model choice for helper agents.
- One place for the human: the status board or the handover file.
- A fresh chat session every day, with a handover.

## Building blocks and where they live in this plugin

| Building block | Purpose | Where |
| --- | --- | --- |
| Global working rules | form of address, autonomy, limits, final report | `templates/CLAUDE.md`, installed to `~/.claude/` by `/setup-workflow` |
| Project instructions (lean) | always-valid project rules, one line per command | `templates/AGENTS.md`, `templates/project-CLAUDE.md` |
| Rules | model choice, session handover, briefing, final report, structured questions | `templates/rules/` |
| Planning folder | roadmap, decisions, questions, findings, to-do | `templates/planning/` |
| Hooks | enforce the model choice, report the context load | `hooks/` |
| Skill `delegate-work` | start file, start, follow-ups, limits, reports | `skills/delegate-work/` |
| Skill `ship-release` | checklist, backup, way back, acceptance list | `skills/ship-release/` |
| Skill `workflow-retrospective` | key figures and at most three evidenced improvements | `skills/workflow-retrospective/` |
| Setup | guided installation | `commands/setup-workflow.md` |

Stage 2 adds, for variant B:

| Building block | Purpose | Where |
| --- | --- | --- |
| `sf-status` | status board, events, wake triggers, supervisor run, strand start, follow-ups, answers | `scripts/bin/sf-status`, `scripts/sf_status/` |
| Heavy-run limiter | at most N heavy runs at once | `scripts/heavy-run.sh` |
| Server templates | supervisor task, wave plan, strand start file, watcher, cron line, deny list | `templates/server/` |
| Skill `delegate-work`, server mode and watcher | start strands on the server, start at a time with a precondition | `skills/delegate-work/` |
| Server setup | from an empty server to the first wave | `docs/05-server-setup.md` |

## First steps

- [ ] Choose the variant (use the decision aid above; `/setup-workflow` offers A and B).
- [ ] Install the plugin and run `/setup-workflow` in the new project.
- [ ] Let the first concept be written with mock-ups and reviewed by a fresh reviewer.
- [ ] Approve the first wave as a quote in the plan.
- [ ] Start every day with a fresh chat session and a handover.
