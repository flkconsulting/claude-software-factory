---
description: Install the software-factory working rules, hooks settings and project templates into the current project and ~/.claude/
---

# /setup-workflow

You guide the user through setting up the software-factory workflow. Work step by step, one question at a time, and wait for the answer before moving on. Templates live in `${CLAUDE_PLUGIN_ROOT}/templates/` (`CLAUDE.md`, `project-CLAUDE.md`, `AGENTS.md`, `planning/`, `rules/`). Read them directly from that path; do not search for the plugin directory.

General rules for this command:
- Never overwrite an existing file silently. For every file that already exists, show a diff and change it only after the user agrees.
- Never write to `~/.claude/` without showing the content (new file or diff) and getting explicit consent.
- Never print or invent secrets. Do not write credentials into any file.
- Lines starting with `Example:` in the templates are guidance for you; never copy them into a written file - replace them with a project-specific line or drop them.
- Replace every `{{PLACEHOLDER}}` in a template with the confirmed value; no placeholder may remain in a written file.

## Procedure

1. **Variant.** Ask which variant to set up. Offer only "A - one machine, subagents and worktrees". Mention that variant B is "stage 2, not yet available". Continue only with A.

2. **Project facts.** Detect the project name, a one-sentence purpose and the build, test and lint commands from the repository (README, package manifests, Makefile, CI files, scripts). Show what you found and let the user confirm or correct each value. If something cannot be detected, ask.

3. **Hooks: block or warn?** Ask "block or warn?" for the rule hooks (model choice for helper agents, context load).
   - Recommend **block**. Reason: plain hints are overlooked during real work; only a block enforced the rule reliably (helper-agent calls without an explicit model, sessions with a very long history). Warn is available for users who prefer hints only.
   - Write `~/.claude/software-factory.json` with `{"mode": "<block|warn>", "context_thresholds": [150000, 300000]}`. The thresholds are defaults and may be changed in that file. If the file exists, show the diff and ask before changing it.

4. **Planning location.** Ask where planning documents (roadmap, decisions, questions, findings, TODO) live: a `planning/` folder in this repository (recommended to start with) or a separate repository. For a separate repository, ask for its location and do not create it yourself. Then set `{{PLANNING_PUSH_RULE}}` to the matching variant from the table; never offer a rule that pushes the code repository without asking.

5. **Project files.** Write, from the templates with placeholders filled:
   - `AGENTS.md` (from `${CLAUDE_PLUGIN_ROOT}/templates/AGENTS.md`)
   - `CLAUDE.md` (from `${CLAUDE_PLUGIN_ROOT}/templates/project-CLAUDE.md`)
   - `planning/` (from `${CLAUDE_PLUGIN_ROOT}/templates/planning/`), only if the planning location is this repository. The copy includes `ERRORS.jsonl` (the empty error index, used by the skill `error-index`). If `planning/` already exists, add only the missing files and never overwrite existing ones (the diff rule applies).
   For each file that already exists, show a diff and change it only after consent; otherwise skip it and record it as skipped.
   If the planning location is a separate repository, tell the user that `ERRORS.jsonl` belongs there (path taken from `{{PLANNING_LOCATION}}`) and offer to create the starter file there after asking; the command never creates that repository itself.

6. **Global rules.** Fill `${CLAUDE_PLUGIN_ROOT}/templates/CLAUDE.md` with the confirmed values (see table) and show it, together with `${CLAUDE_PLUGIN_ROOT}/templates/rules/*.md`, as a proposal for `~/.claude/` (`CLAUDE.md` and `rules/`): list new files, and show a diff for files that exist. Write only what the user explicitly approves, file by file.

7. **Companion plugins and tools.** Check what the method relies on and report what is missing; never install anything yourself.
   - Plugins: read `~/.claude/plugins/installed_plugins.json` (if it is missing or unreadable, say so and list all plugins as "not verified"). Required: `superpowers`. Recommended: `context7`, `claude-md-management`, `playwright`.
   - Tools: check with `command -v` for `git`, `gh`, `gitleaks` and `python3` (version 3.10 or newer).
   - For each missing item print one line with its purpose and the install command from the README section "Companion plugins and tools" (plugins: `/plugin install <name>@claude-plugins-official`; tools: the system package manager). Mark required items as required.

8. **Wrap-up.** Print two lists: files written and files skipped (with the reason). Add the list of missing companion plugins and tools from step 7. Name the path of the error index (`ERRORS.jsonl` in the planning location). Remind the user that the hooks take effect in new sessions.

## Placeholders

Ask each question once (`{{PLANNING_PUSH_RULE}}` is not asked; choose the matching variant from step 4); reuse the answer wherever the placeholder appears.

| Placeholder | Question | Default |
| --- | --- | --- |
| `{{USER_NAME}}` | How should Claude call you? | none, required |
| `{{ADDRESS_FORM}}` | Which form of address (for example informal "you" or formal)? | informal |
| `{{REPLY_LANGUAGE}}` | In which language should Claude reply to you? | English |
| `{{PUSH_POLICY}}` | May Claude push? | Default: no push without explicit instruction. Alternative: push the own feature branch when tests are green and the secret scan passed |
| `{{AUTONOMY_LIMITS}}` | Which actions need explicit instruction? (one bullet per action) | edit files outside the repo; change production systems or data, or deploy; wipe or reset databases or storage; create, copy or expose secrets; irreversible git commands, push (except as allowed by the push policy in section 5), delete branches, merge PRs; create or scale paid cloud resources; add dependencies with far-reaching license or security consequences |
| `{{PROJECT_NAME}}` | What is the project called? | detected from the repository |
| `{{PROJECT_PURPOSE}}` | What does the project do, in one or two sentences? | detected from the README |
| `{{BUILD_COMMANDS}}` | Which commands build, test and lint the project? | detected from the repository |
| `{{PLANNING_LOCATION}}` | Where do planning documents live? | `planning/` in this repository |
| `{{PLANNING_PUSH_RULE}}` | derived from the planning location (no question) | Separate planning repository: "Agents commit and push there without asking (pull first)." `planning/` in this repository: "Planning changes are committed with the normal work and follow the push policy." |
