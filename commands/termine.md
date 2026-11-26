---
description: Open the week view of the reminders (appointments) in the browser
---

# /termine

Run exactly this command with the Bash tool:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/hooks/reminders.py" --html
```

Then name the printed path in one sentence. On macOS the page opens in the browser by itself; elsewhere the user opens the path. If the command fails, show its error message.
