---
name: log-ai-usage
description: Append an entry to AI_USAGE.md recording an AI-assisted engineering activity (prompt, response summary, accepted/edited/rejected decision, files affected, verification). Use after any meaningful AI contribution: design decisions, generated code or tests, review findings, rejected suggestions.
---

# Log AI usage

The assessment requires a record of every AI-assisted activity. Append (never rewrite) one entry per
activity to `AI_USAGE.md` in the repo root.

## Steps
1. Read `AI_USAGE.md` to find the last entry number. Create the file from the header in step 3 if it is missing.
2. Gather the facts for the activity in `$ARGUMENTS` (or the most recent AI-assisted step in this conversation):
   - **Prompt**: the user's prompt, quoted verbatim or lightly trimmed. Remove any personal names,
     emails, credentials, or secrets and write `[redacted]` in their place.
   - **AI response**: 2–5 bullet summary, plus a short excerpt if a specific line of code or wording matters.
   - **Decision**: exactly one of `Accepted`, `Edited`, `Rejected`, or a per-suggestion breakdown
     if the response had several suggestions. Say *what* was edited or *why* it was rejected.
   - **Files / decisions affected**: paths or design decisions.
   - **Verification**: how it was checked independently: test command + summary line, manual
     reasoning, reviewer subagent result, or `Pending` if not yet verified (update it later).
3. Append using this exact format:

```markdown
### <N>. <Short activity title>
- **Date:** <YYYY-MM-DD>
- **Activity type:** <Requirements analysis | Design | Code generation | Test generation | Review | Debugging | Documentation | Tooling>
- **Prompt:**
  > <prompt>
- **AI response (summary):**
  - ...
- **Decision:** <Accepted | Edited | Rejected>: <what and why>
- **Files / decisions affected:** ...
- **Verification:** ...
```

4. If an earlier entry was `Pending` verification and has now been verified, update that entry's
   Verification line in place. This is the only edit to past entries that is allowed.
4a. If the decision is `Edited` or `Rejected` (or the candidate overrode the AI), also add a row to the
   matching table in the **Summary** section at the top of `AI_USAGE.md`, linking to the new entry.
5. Tell the user the entry number you added, in one line.

## Honesty rules
- Never describe AI output as the user's own work, or the reverse.
- Record rejected and edited suggestions. They show independent review, which the assessors look for.
- Don't invent verification. If something wasn't tested, say so.
