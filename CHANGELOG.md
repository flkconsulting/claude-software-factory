# Changelog

All notable changes to this project are documented in this file.

## [Unreleased]

### Added
- Plugin and marketplace manifests (version 0.1.0).
- Skill pre-check: five evidence questions before planning or implementing, without scoring.
- Skill error-index: per-project JSONL index of solved error causes with a search/append script that rejects obvious secrets; planning template ERRORS.jsonl.
- Documentation (docs/01 to docs/04), README and CI workflow (tests on Python 3.10 and 3.13, secret and blocklist scan).
- README section "Companion plugins and tools" (required: superpowers, git, gh, gitleaks, Python 3.10+; recommended: context7, claude-md-management, playwright) and a check step in `/setup-workflow` that reports missing items without installing them.

### Changed
- Project templates: pointers to pre-check and the error index; definition of done requires every requirement checked off.
