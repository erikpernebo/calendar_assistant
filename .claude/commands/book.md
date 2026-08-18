---
description: Confirm one of the held slots, put it on the calendar, and re-place whatever it displaced.
argument-hint: "<which slot> [what to call it]"
---

Book: $ARGUMENTS

## 1. Resolve the slot

Read `$VAULT/state/holds.json` and match the user's words to one hold. If the match is ambiguous,
list the candidates and ask — booking the wrong slot means emailing a recruiter twice.

If the user names a time that was never held — the other party proposed something else — treat it as
a new slot. Re-run the checks from `find-time` step 2 against that exact interval and report its
cost **before** creating anything. An externally proposed time is the most likely way a lecture
quietly gets missed.

## 2. Create the event

Resolve the `Semester` calendar by name via `list_calendars`. Create the event there, following the
event formatting rules in CLAUDE.md: plain title (`Acme call`, `Acme phone screen`), no
emoji, no prefix. Description is the task ID alone.

Record it as a task in `$VAULT/tasks/open.md` with `type: meeting`, `context: anywhere` for a call
or the real context for anything in person, `estimate` equal to the meeting length, and
`status: not-started`. This is what puts it in the hour budget — a meeting that lives only on the
calendar is time the scheduler thinks it still has.

Add the row to `$VAULT/state/calendar.json` in the same turn.

## 3. Settle the displacement

For each item the slot displaces:

**Own work blocks** (`cost: free`, an `event_id` in `state/calendar.json`) — delete or move them and
re-place their hours inside the window, following the `scheduling` skill. If the hours no longer fit
before the deadline, say so now rather than after the week is already lost.

**A shifted commitment** (`action: shift`) — move it if it is an event the agent owns. If it is on
another calendar, say what needs to move and let the user do it.

**Anything missed** (`cost` above `free`) — the agent does not delete it; it stays on its own
calendar and the user simply does not attend. Record the miss in two places:

- append to `$VAULT/log/YYYY-MM-DD.md`: what was missed, and for what
- note it in the current week note under a `Missed` heading

Then check the record: if the same recurring commitment has been missed before in the last month,
say so. Missing one recitation is a trade; missing three is a pattern the user should see, and it is
not the agent's place to let that accumulate quietly.

## 4. Prep

If this is a recruiting call, interview, or anything the user would want to walk into prepared,
create a linked prep task — 30 minutes by default — and place it in the day or two before. Interview
prep is a tier-1 goal in `goals.md`; this is that goal doing its job, not extra work.

Say what you created. If the user does not want it, they will say so.

## 5. Release and report

Set the booked hold's `status` to `booked`. Set every other hold in the same `group` to `released`,
freeing that time immediately.

Report a short diff: the event created, what moved and where it went, what will be missed, the prep
block, and anything now at risk. Then mirror the meeting to Reminders per CLAUDE.md if it carries
anything the user needs to bring or prepare.

Commit the vault: `book: <label>`.
