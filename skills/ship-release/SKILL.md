---
name: ship-release
description: Use when a version of the project is to be released - running the checklist for tests, version number, changelog and tag, then handing over to the project-specific deployment step with a backup first, a way back and an acceptance list for the user.
---

# Ship a release

Releasing and deploying need the user's explicit approval (quote it in the start file, see `delegate-work`). Do the checklist first; deployment is a project-specific last step.

## 0. Clarify first

- Release branch and its current state on the remote (note the commit).
- Read the release notes of the version: migrations, new configuration values, changed infrastructure files? List "what the target environment needs". Only read the target, change nothing.

## 1. Checklist

1. **Tests and checks:** the build, test, lint and format commands from the "Commands" section of the project `AGENTS.md`. Run the full test suite only if the code changed since the last green full run on the same state; otherwise point to that run. Repeat known flaky tests on their own; do not change them inside a release.
2. **Version:** one version number, identical in every place the project keeps it (manifest, package files, docs). Check with a search for the old number.
3. **Changelog:** a section for the version with what changed for users and operators; migrations and new settings named explicitly.
4. **Security checks:** dependency audit and image scan, compared with the previous version (same / new / gone); blocking findings only with a documented exception.
5. **Tag:** create the version tag on the release commit only on explicit instruction; never move or delete tags.
6. **Build artifacts** (if the project builds any): checksums written next to them.

## 2. Deploy (project-specific)

- Read the deployment command from the "Commands" section of the project `AGENTS.md`. If it is not there, **ask** the user; never guess a command or a target.
- Before deploying: **backup** of data and configuration to a place that survives the rollback, plus the state before (record counts, checksums). Check free disk space first.
- Deploy, then verify: all services healthy and on the new version, migrations applied, state after equals state before, logs of the last minutes without errors, the project's smoke test passes.
- **Do not change** on the target: user roles, data volumes, restart policy, backup settings, unless the release notes demand it and the user approved.
- **Way back** (describe it in the report): restore configuration and the backup; for database migrations restore the dump, never downgrade the schema as the way back.
- Clean up after success: remove only old images or artifacts of versions older than the previous release, one by one, never with a blanket prune.

## 3. Close

- Update the release status line in the project plan, commit and push only the release branch.
- Report with first line `RELEASE <version> DONE`, `RELEASE <version> BLOCKED` or `RELEASE <version> IN PROGRESS` (while the release runs or the acceptance waits for the user): times in UTC, backup location, state before/after, checks with numbers, comparison of findings, way back, commits.
- Section "Acceptance for the user": numbered list, each item with the click path or command, what is new, and how to recognise it.
