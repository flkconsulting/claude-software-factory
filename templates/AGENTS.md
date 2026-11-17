# {{PROJECT_NAME}} - Working instructions

## Purpose
{{PROJECT_PURPOSE}}

Example: Web shop backend and admin UI; details per area live in the developer docs.

## Planning
- Roadmap, decisions (D-x), questions (Q-x), findings (F-x) and TODO live in the planning folder: {{PLANNING_LOCATION}}. Read its README before any work.
- {{PLANNING_PUSH_RULE}} Agents never write a D-entry themselves.
- Every reply to the user starts with the new Q-entries of the step (one line each, with number).

Example: Before starting, read the TODO file and the "Present to user" section of the questions file.

## Hard limits
- **Secrets:** none in the repository; never log them or print them in error messages.
- **Real customer data:** never check it in; tests and demos run only on synthetic data.
- **Destructive operations:** deleting data, volumes or branches only on explicit instruction; no force-push.
- **Production:** never change production systems or data without explicit approval.

Example: Tests never run against an installation that holds real customer data.

## Commands
{{BUILD_COMMANDS}}

Example: `make test` runs the unit tests; `make lint` runs linter and format check.

## Conventions
- Follow the existing naming and structure of the repo; reuse existing patterns before adding new ones.
- Configuration only through the existing mechanism; new settings get safe defaults and are documented.

Example: A new setting is added to the example config file with a default that changes nothing.

## Documents
| Topic | Location |
| --- | --- |
| Roadmap | planning folder, roadmap file |
| Developer docs | `docs/` |

Example: When setup, configuration or interfaces change, update the matching document in the same change.
