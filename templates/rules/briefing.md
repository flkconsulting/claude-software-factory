# Briefing texts for agents: only the essentials

Applies to start files, follow-up messages, an orchestrator's brief and **every brief to a helper agent** (agent tool, subagent-driven development).

Every word in a brief is re-read by the model on every step - long briefs cost money and dilute what matters.

1. **Reference instead of copy:** name path and section (`docs/.../concept.md`, section 3); do not copy paragraphs from concepts, plans or project instructions. Exception: the user's approval quote (verbatim, one sentence).
2. **Size limits:** start file about 3 KB (without the fixed limits that come from a template) - follow-up message about 0.5 KB - brief to a helper agent about 1 KB. Above that: shorten, do not justify.
3. **A brief to a helper agent contains only:** goal (one sentence) - affected files or plan task with path - what is already ruled out or decided - expected result (form, length) - limits (do not commit, only these files) - model per the model-choice rule. No backstory, no reasons the agent does not need to act.
4. **Request short answers:** "Reply only with result, evidence (file:line, test count) and open points, at most 15 lines." No retelling of the work steps.
5. **Consolidate follow-ups:** if a standing brief (orchestrator, strand template, long-running start file) has **three or more additions**, rewrite it as one text: drop what is outdated, put what applies in its place in the flow, keep quotes only for approvals. Keep the old version next to it as an archive copy (not to be read by agents).
6. **Check:** run `wc -c` before starting or delivering. Report start files over 4 KB and an orchestrator's own brief over 10 KB as a notice, and consolidate per point 5.

**Why:** Long briefs are re-read at every step by every agent, so they raise cost and bury the important instructions; short, reference-based briefs keep agents focused and cheap.
