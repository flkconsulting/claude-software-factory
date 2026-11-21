---
name: pre-check
description: Use when about to write a plan, start an implementation or fix a bug - answers five questions with evidence first (already exists, fits the architecture, official documentation read, prior art, cause or requirement clear) and clears every "open" item before work starts.
---

# Pre-check

A cheap check before expensive work. The result is a list of answers with evidence, never a number.

## The five questions

Answer each one with evidence. A guess is not evidence; a guess is `open`.

### 1. Does it already exist?

Evidence: the search terms you used and where you found hits (repo search, tests, documentation). If nothing exists, name what you searched.

### 2. Does it fit the architecture and conventions?

Evidence: the file and section of the project rules that apply, and an existing example in the repo that does something similar.

### 3. Official documentation read?

Evidence: title or link of the page, and the concrete statement that supports the solution. Memory of the documentation does not count.

### 4. Prior art in other projects?

Evidence: where you found it (repository, library), or `none found, searched: <where and how>`.

### 5. Cause or requirement clear?

Evidence: for a bug, a reproduction or the exact error text, and for a feature, the requirement in your own words with its source. For errors, search the error index first (skill `error-index`).

## Output format

One line per question:

```text
1. <yes/no/n.a.> - <evidence>
2. <yes/no/n.a.> - <evidence>
3. open - <what is missing>
4. ...
5. ...
```

## Rules

- Every question gets evidence or `open`. `n.a.` is allowed only with one sentence of reasoning.
- Clear every `open` item before the plan or implementation starts: read, search, or write a test that answers it.
- If it stays `open` and you cannot decide it yourself, ask the user - structured, one line per option, with your recommendation.
- Proportion: for a one-line change, one sentence per question is enough. Do not create a document; the result goes into the plan header or the first reply.

**Why:** Skipping the check before building leads to duplicate work and plans built on assumptions. A list with evidence shows the gaps; a percentage hides them.
