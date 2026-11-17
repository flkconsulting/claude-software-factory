# Session handover on a long history

Applies in all projects. Every step re-reads the whole history so far, so very long sessions become disproportionately expensive.

The plugin's context-load hook reports once per session per threshold (a "context load ... threshold N" note appears in the context):

- **First threshold (default 150,000 tokens):** as soon as the current topic is finished, write a handover and explicitly suggest to the user, at the end of the reply, to close the session and begin a new one.
- **Second threshold (default 300,000 tokens):** immediately - write the handover and suggest the switch at the end of this reply.
- **Without a note:** at a natural break (a larger topic is done and the next has nothing to do with it), suggest the switch as well.

The suggestion is its own, clearly visible line, e.g. "**Good time for a new session** - history about N tokens, handover is in ...". Do not repeat it if the user wants to continue.

**Handover beforehand:** state, open points, reminders/scheduled tasks (which live only in the session), and where the new session picks up - in the project's handover file (if present), otherwise in the project's memory note. The suggestion names the location.

**Start sentence for the new session:** every suggestion ends with a ready-made sentence to paste into the new session, as its own code block. The sentence names where the state is (file and section), what to begin with, and what the new session does not see by itself (e.g. files only in the old session's working folder, open PRs). First verify that everything named really is in the file; transfer content from the session's working folder there beforehand.

**Sessions without a human** (terminal-multiplexer strands, orchestration): at the second threshold, after the next completed step secure the state, note "restart recommended (context about N tokens)" in the report/status board; the requester restarts it with the same start file.

**Why:** Sessions with hundreds of thousands of tokens of history cost more per step than any model choice, because each step re-reads everything; a clean handover into a fresh session keeps cost down without losing state.
