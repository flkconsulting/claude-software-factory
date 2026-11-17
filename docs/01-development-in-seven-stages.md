# 01 - Development in seven stages

**Occasion.** The working method of this plugin was not designed up front. It grew from a chat with an AI assistant into a small software operation in which one human decides, one Claude session plans and steers, and several Claude sessions build in parallel. This document records the seven stages and the turning point of each, so you can see which problem each rule answers.

**Effect.** Each stage started with a bottleneck the human noticed and ended with a new role for Claude. The tools did not come first; they followed the problems. Reading the stages tells you which parts of the method you need today and which can wait.

**Limits.** This is a history, not a recipe. Stages 3, 5 and 7 depend on a separate always-on machine and are **Stage 2** material: this plugin (Stage 1) covers the single-machine variant only. See [04 - Transferring the method](04-transferring-the-method.md).

## The stages

### 1. The assistant in a chat

Claude writes concepts, the human reads and approves. Every conversation produces a document in the repository, every approved concept a plan made of small, checkable tasks.

**Turning point:** the plan becomes the interface between thinking and building. Whoever implements it no longer needs to understand what was said in the conversation.

### 2. Subagents instead of solo work

Claude stops implementing plans itself. It hands each task to a fresh subagent, has a second one review it, and keeps a progress log. Work happens in a separate working folder (git worktree) per undertaking.

**Turning point:** errors are found by an independent reviewer, not by the author.

### 3. A separate work machine (Stage 2)

Long runs block the main machine. A dedicated server takes over: Claude sessions run there inside a terminal multiplexer, receive a start file that quotes the human's approval, and report back in a file whose first line is `DONE` or `BLOCKED`.

**Turning point:** work runs overnight.

### 4. Trust becomes a rule

The human overlooks to-dos in the chat, so the to-dos move to a page of their own. The human no longer wants to publish website texts by hand, so Claude may publish directly, with a backup first and a report afterwards. Each such permission is recorded as a rule together with its reason.

**Turning point:** autonomy grows in small, named steps, never wholesale.

### 5. Parallel in one night (Stage 2)

A feature is pulled forward into the next release. Claude splits it into one foundation, several parallel strands and one merge; a watcher script starts the strands as soon as the foundation is done. By morning the work is ready and all tests are green.

**Turning point:** from a construction worker to a site manager.

### 6. Cross-section first, then plans

Before more plans are written, the human asks that the implementation be prepared so that the commonalities across all concepts are worked out first, to avoid going three steps forward and one back. Several subagents read all concepts and the code; Claude derives shared building blocks from them; an independent reviewer finds wrong decisions; the human decides the open questions.

**Turning point:** architecture is checked before building, not repaired afterwards.

### 7. Supervisor and status board (Stage 2)

The human asks what happens when the laptop is closed at night. Steering moves to the server: a "supervisor" Claude session runs the wave plan, and a script without AI watches it. The human sees everything on one page and answers there directly.

**Turning point:** the human leads without having to be present.

## What Stage 1 takes from this

| Stage | Carried into this plugin as |
| --- | --- |
| 1 | Concept before plan, plan before code (templates, `/setup-workflow`) |
| 2 | Independent review, working folder per undertaking (`delegate-work` skill) |
| 4 | Permissions as rules with a reason (`templates/CLAUDE.md`, limits in `delegate-work`) |
| 6 | Cross-section before building (part of the method, see [03](03-working-method.md)) |
| 3, 5, 7 | Not in Stage 1; planned for Stage 2 |
