# Wave plan

Purpose: the only source of approvals for the supervisor. It starts a strand only for a row whose approval cell begins with `yes` and whose "starts when" condition is met.

Approval: the human's words verbatim go into the cell `approval` of the row, for example `yes - "<quote>"`. Without a quote there is no `yes`.

| short | strand | approval | starts when | branch | migrations | may change |
| --- | --- | --- | --- | --- | --- | --- |
| example | Example strand | no | after report `<state-dir>/reports/<project>/<other-short>.md` starts with `<OTHER> DONE` | feature/example | none | src/example/ |
