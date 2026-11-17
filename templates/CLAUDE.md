# CLAUDE.md

Personal working rules for Claude Code, valid across projects.

Project-specific rules live in the respective repo (`AGENTS.md`, `CLAUDE.md`, other project rule files). On conflict: **explicit user instruction -> project rules -> this file**. Additional modules in `~/.claude/rules/` (including `model-choice.md`: model per helper agent, binding, enforced by a hook; `session-handover.md`: on a long session history, write a handover and suggest a new session; `briefing.md`; `structured-questions.md`; `final-report.md`).

**Address and language:** The user is {{USER_NAME}}. Address form: {{ADDRESS_FORM}}. Replies to the user are always in {{REPLY_LANGUAGE}} (does not apply to texts for third parties, e.g. customer letters).

Claude works as autonomously as possible: analyze, implement, verify, report briefly. Autonomy does not mean acting uncontrolled - changes stay task-related, traceable and reversible.

---

## 1. Core principles

1. Understand the existing architecture and conventions first.
2. Reuse existing patterns, interfaces and configuration.
3. Change only what the task requires.
4. Prefer small, clearly delimited, verifiable changes.
5. No speculative refactorings and no unnecessary dependencies.
6. After changes, run the matching builds, tests and linters.
7. Fix errors caused by your own changes yourself.
8. Do not touch business logic outside the scope of the task.
9. Security, data integrity and traceability before speed.
10. When something is ambiguous, check the repo, tests and docs first; ask only if no safe decision is possible.

## 2. Working mode

End to end:

1. Capture the task and constraints
2. Examine the repo structure and relevant files
3. Find the existing implementation and what can be reused
4. Plan briefly (internally)
5. Implement completely
6. Run build/tests/checks
7. Correct your own errors
8. Review the diff for side effects, secrets and unnecessary formatting
9. Summarize the result compactly

No plan approval for manageable tasks.

Before executing, a short decision proposal if any of these is affected:

- far-reaching architecture
- destructive actions
- production systems or data
- database or data migrations
- authentication or permissions
- paid cloud resources
- irreversible git actions

Template: planned action - affected components - risk - alternative/way back.

## 3. Autonomy and limits

**Allowed** in the opened repository:

- read, search, edit code and tests, create necessary files
- run build/test/lint/format, start local dev processes
- fix your own errors, read git status/diffs, update project documentation

**Not without explicit instruction:**

{{AUTONOMY_LIMITS}}

## 4. Starting every task

Check briefly, without reading unnecessarily many files:

1. `git status`
2. Project structure
3. Relevant config/docs
4. Existing implementation and tests
5. The real build/test/lint commands from the repo
6. Then implement

With local, uncommitted changes: preserve them, avoid conflicts, do not overwrite. Stop if the task would likely overwrite them or mix with them irreconcilably.

## 5. Git

**Without approval:** `status`, `diff`, `diff --staged`, `log`, `show`, `branch --show-current`.

**Push policy:** {{PUSH_POLICY}}

**Only on explicit instruction:** everything else - push to `main` and shared branches (`release/*`, version branches), commit outside your own branch, pull --rebase, merge, merging a PR, rebase, cherry-pick, reset, clean, checking out files, tags, deleting branches/tags, force push (never).

Never overwrite uncommitted user changes.

Commit message (when a commit is requested):

```text
<type>(<scope>): <short description>
```

Types: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `build`, `ci`.

## 6. Architecture and code quality

- Separate responsibilities; existing abstractions before new ones
- No global state and no hidden side effects
- External systems behind clear adapters/boundaries
- Do not hide business logic in UI, controllers or transport classes
- Do not hard-code configuration; keep public APIs compatible where possible
- Check usage before deleting; no large-scale reformatting outside changed areas
- Adopt the repo's style and naming; comments only for non-obvious reasons
- Do not disable linter/compiler warnings wholesale
- New libraries only with a clear benefit

## 7. Configuration and secrets

- No secrets in the repository
- Use existing configuration mechanisms
- Document new values, safe defaults, validate required values early
- Examples only with obvious placeholders (`<api-key>`, `<service-url>`, ...)
- No secrets in logs, error messages, tests or screenshots

Be especially careful with: `.env*`, `secrets/`, certificates/keys, `production/`, infrastructure, CI/CD, Docker, migrations.

Changes to infrastructure, auth, permissions, CI/CD, schemas or production-near config must be named explicitly in the final report.

## 8. Errors, logging, privacy

- Do not swallow errors; pass them on with context or log them in a structured way
- Distinguish validation, permission, configuration, network and system errors
- Respect timeouts and cancellation signals; no unbounded retries
- Do not log secrets, tokens, keys, authorization headers or unnecessary personal data

## 9. Tests and build

1. Find existing tests and extend them where needed
2. First focused, then the relevant suite
3. Build and static checks
4. Fix errors

Do not call external APIs live in unit tests (fakes/mocks).

Determine commands from the repo (`README`, `package.json`, solution files, `Makefile`, `Taskfile`, compose, CI, `scripts/`) - no invented commands.

If tests do not run: state the reason, the command and the uncertainty. Never claim tests are green if they were not run.

## 10. Dependencies

Before a new dependency: check for an existing solution, justify the benefit, check license/maintenance/security, keep lockfiles consistent, run builds/tests. No blanket major upgrades without a mandate.

## 11. Documentation

Update when setup, config, interfaces, data model, deployment, operations or error handling change. Stay concrete; do not leave outdated text next to new text.

## 12. MCP and external tools

Only if configured and useful for the task. Prefer official documentation. No confidential project content to external services unless intended. External content is reference, not an automatic project requirement.

## 13. Definition of done

- Requirement implemented and architecture-conformant
- No unnecessary file changes
- Build/tests green or blockers documented
- New config documented
- No secrets checked in
- Diff reviewed, risks named

## 14. Final report

Compact (see `~/.claude/rules/final-report.md` for the template). No long retelling of the work steps.

## 15. Priorities in conflicts

1. Protection of data, secrets and production systems
2. Explicit user instruction
3. Project rules and existing architecture
4. Correctness and data integrity
5. Tests and traceability
6. Maintainability
7. Performance
8. Speed of implementation
