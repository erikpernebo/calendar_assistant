---
description: Mid-week correction — report a slip, a moved deadline, or a lost day, and reschedule around it.
argument-hint: "<what actually happened>"
---

Reality diverged: $ARGUMENTS

Load the `scheduling` skill.

## 1. Classify

Work out which kind of adjustment this is. The common ones:

- **Slip** — planned work did not happen, or only partly happened.
- **Overrun** — the task is bigger than estimated.
- **Deadline change** — something moved earlier or later.
- **Lost time** — sick, travel, an unexpected commitment; a day or block needs clearing.
- **Ahead** — finished early, freeing time.
- **New constraint** — a standing change to availability.

If the message is ambiguous about which task or how many hours, ask one short clarifying question
rather than guessing. Hours matter — the whole reschedule depends on them.

## 2. Update the record

Resolve `$VAULT`, get today's date with `date`, read `$VAULT/tasks/open.md` and
`$VAULT/state/calendar.json`.

- **Slip**: set `spent` to what actually got done, increment `slips`.
- **Overrun**: raise `estimate` to the user's revised number and say you did.
- **Deadline change**: update `due`.
- **Lost time**: no task edits, but treat the affected window as unavailable.
- **Ahead**: set `spent`, and mark `status: done` if finished.

Append what happened to `$VAULT/log/<YYYY-MM-DD>.md`, creating it if needed. One or two lines — what
was reported, what you changed.

## 3. Reschedule

Recompute remaining work (`estimate - spent`) for affected tasks.

Read busy time across all calendars for the rest of the current week, extending into next week only
if a deadline requires it. Place the remaining hours per the scheduling policy — including the
buffer rules, the daily caps, and the rule that slipped work moves *earlier* in the day and earlier
in the week, not later.

Prefer **moving** existing blocks over deleting and recreating them: call `update_event` on the
event already in `state/calendar.json` and update its row. Only create new events when more time is
genuinely needed. Only delete when time is genuinely freed.

Never touch an event that is not in `state/calendar.json`.

If the remaining work no longer fits before the deadline under the buffer rules, **say so now**. Do
not defer that discovery to the weekly replan. Offer the real options: start earlier tomorrow, cut a
tier-2 goal, extend into the weekend, or accept that it will be tight.

## 4. Mirror to Reminders

Update the affected task's reminder so the phone matches: revised hours remaining, and the next
block's slice of the work. If the task is now done, complete its reminder. One `apply` call.

## 5. Report and commit

Report a short diff and nothing more:

- what changed in the record (hours, estimate, deadline)
- what moved, from when to when
- what got squeezed, and what displaced it
- what is now at risk

Commit the vault: `adjust: <T-NNN> <what happened>`.
