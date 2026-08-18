---
description: Read-only semester status — what is due, what is behind, goal hours against target.
argument-hint: "[optional: a horizon like 'next 3 days' or a course code]"
---

Report the current state of the semester. **Make no changes.** Do not create, move, or delete
calendar events. Do not edit any vault file. This command is read-only.

Scope: $ARGUMENTS — if empty, use the next 7 days.

1. Read `vault.local.json` to resolve `$VAULT`. Get today's date with `date`.
2. Read `$VAULT/tasks/open.md`, `$VAULT/goals.md`, and `$VAULT/state/calendar.json`.
3. Call `list_calendars`, then `list_events` on the `Semester` calendar over the scope window.

Then report, concisely:

**Due soon** — every task with a deadline in the window: ID, course, name, when it is due, hours
remaining (`estimate - spent`), hours currently scheduled. Flag any task where scheduled hours are
less than remaining hours.

**Behind** — every task with `slips > 0` or with `status: in-progress` and remaining hours that no
longer fit before the deadline under the buffer rules in the scheduling skill. Say how short each
one is.

**Blocked** — tasks with `status: blocked`, and what they are waiting on.

**Goals** — for each goal in `goals.md`: hours scheduled this week against weekly target, and
whether it is on track.

**Drift** — if any block in `state/calendar.json` no longer exists on the calendar, or any
`Semester` event is missing from the state file, list the discrepancies. Do not fix them here; tell
the user to run `/adjust` or `/plan-week`.

Keep it scannable. If nothing is behind, blocked, or drifting, say so in one line rather than
printing empty headings.
