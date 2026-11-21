---
name: error-index
description: Use when an error, failing test or unexpected behavior appears (search the project's error index before debugging) and after a cause has been found and fixed (append one line) - keeps a searchable JSONL list of solved causes per project.
---

# Error index

A searchable list of solved error causes, one JSON line each. It stops the same cause from being hunted down twice.

**Why:** The same cause is otherwise searched for again and again; a searchable one-liner saves the repetition.

## Location

The script resolves the path in this order: `--file`, then `$SF_ERROR_INDEX`, then `planning/ERRORS.jsonl` relative to the current directory. Always pass `--file` when the project rules (AGENTS.md) name a path; otherwise running from a subfolder or a separate planning repo silently creates a second index. If the file is missing, `add` creates it.

## Before debugging

```bash
python3 ${CLAUDE_SKILL_DIR}/error_index.py search --file <index path from AGENTS.md> <term> [<term>...]
```

Use one to three terms from the error text; all terms must match (case-insensitive). Exit 1 means no hit: continue normally. A hit is a hint, not proof: still verify the cause against the case at hand.

## After the fix

```bash
python3 ${CLAUDE_SKILL_DIR}/error_index.py add --file <index path from AGENTS.md> --symptom "<shortened error text>" --cause "<root cause>" --fix "<what was changed>" --ref "<commit or file>"
```

One line per solved cause, not per attempt. Only confirmed causes, never guesses.

| Field | Meaning | Example |
| --- | --- | --- |
| `date` | ISO date, defaults to today | `2026-01-15` |
| `symptom` | Shortened error text, max 200 characters | `Timeout while connecting to the database` |
| `cause` | Confirmed root cause | `Wrong port in the config file` |
| `fix` | What was changed | `Set the documented default port` |
| `ref` | Commit or file | `config/app.cfg` |

## Privacy

No secrets, tokens, names, personal or customer data. Shorten and clean the error text before adding it. The script rejects recognizable cases (bearer headers, credential assignments, URLs with credentials, private keys, long token-like strings, email addresses, IPv4 addresses) and names only the pattern, but it does not replace your own judgment. If a harmless message is rejected (for example "Unexpected token: }"), reword it.

## Scope

Lessons in prose still belong in `FINDINGS.md`; the index is the short form for searching.
