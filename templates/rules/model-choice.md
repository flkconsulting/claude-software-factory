# Model choice for helper agents

Applies in all projects. The main session's model is chosen by the user; this rule concerns every helper agent (agent tool, skills that dispatch subagents, workflows).

Every helper agent gets its model **explicitly** (`model: haiku | sonnet | opus`), never inherited. The plugin's model-choice hook rejects (or warns about) calls without a model. When unsure which model fits, choose Sonnet.

| Model | Used for |
| --- | --- |
| **Haiku** | Purely mechanical work with a clear spec: transferring text, renaming, one file from a complete plan text, collecting images, searches with an unambiguous target |
| **Sonnet** | Default: implementation and review per task, inventories, research, fix rounds 1-3 |
| **Opus** | Only architecture and security decisions, fix rounds 4-5, final review of a whole undertaking |

Typical work - Sonnet, with limits downward and upward:

| Work | Sonnet | Haiku instead of Sonnet | Opus instead of Sonnet |
| --- | --- | --- | --- |
| Code reviews | Review per task or file | - | Final review of a whole branch; anything touching permissions, privacy, security |
| Test generation | Tests for new logic, edge cases | Test data/fixtures from a pattern, tests from a finished plan text | - |
| Documentation | Manuals, operations docs, texts for non-programmers | Updating paths, version numbers, tables | - (concepts are written in the main session, not by a helper agent) |
| Medium-complexity refactoring | Within one module | Renaming/moving without logic changes | Across module boundaries, migrations, login and permissions |
| Analysis of single components | Understand, assess, find weaknesses | Pure searching ("where is X used") | - |
| Ticket preparation | Understand the requirement, acceptance criteria | Only reformatting or transferring | - |

- When in doubt, Sonnet. Opus needs a justification in the report.
- **The main session does not write itself:** if the main session would write more than a few paragraphs of docs/text, or several passes on a graphic, it hands that off - rewriting from a bullet list to Sonnet, building PDFs and rendering images to Haiku. The main session keeps gathering state, bullet points and acceptance.
- Forks of the own session (`subagent_type: "fork"`) always run with the session's model and are exempt from the model-choice hook - use them only when the full context is really needed.
- Keep briefs to helper agents short: goal, files, what is decided, expected result, limits; answer at most 15 lines.
- Reports on longer work state the distribution (number of helper agents per model).

**Why:** Every step of the main session re-reads its whole history with the session's (usually most expensive) model, so letting long documents and repeated graphic passes run there dominated cost; an explicit model per helper agent keeps routine work on cheaper models.
