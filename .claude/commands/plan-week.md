---
description: The weekly rewrite — check in on last week, then plan and schedule the coming week.
argument-hint: "[optional: a week like '2026-W36', defaults to the coming week]"
---

Plan the week. Target: $ARGUMENTS — if empty, Monday through Sunday of the coming week.

Load the `scheduling` skill before placing anything.

## 1. Read state

Resolve `$VAULT` from `vault.local.json`. Get today's date with `date`.

Read: `$VAULT/semester.md`, `$VAULT/goals.md`, every note in `$VAULT/courses/`,
`$VAULT/tasks/open.md`, the most recent note in `$VAULT/weeks/`, and `$VAULT/state/calendar.json`.

Call `list_calendars` and resolve the `Semester` calendar ID.

## 2. Check in

Ask the user these questions in one message, as a short numbered list. Do not ask them one at a
time, and do not pad them with preamble.

1. What did you finish since the last plan?
2. What slipped, and roughly how many hours short?
3. Anything new coming that I do not have — assignments, exams, changed deadlines?
4. Any low-energy days, travel, or unusual commitments this week?
5. Any goal to dial up or down?

Pre-fill what you can from `state/calendar.json` and last week's note: list the blocks that were
scheduled and ask the user to confirm rather than recall from nothing.

Wait for the answer before proceeding.

## 2b. Reconcile Reminders first

Run steps 1-4 of `/sync` before reconciling: dump, reconcile, pick up anything added directly to a
list, merge edits, and handle completions. Chores and errands are part of the week's demand — a
grocery run competes with a problem set for the same hours.

## 3. Reconcile

From their answers:

- Mark finished tasks `status: done`, set `spent`, and move them from `tasks/open.md` to
  `tasks/done.md` with a completion date.
- For each closed task where `spent > estimate`, update the course's `estimate_bias` using the
  damped formula in the scheduling skill, and append a line to that course note's calibration log.
- For slipped tasks, update `spent` and increment `slips`.
- Add any new work as new task entries, allocating IDs monotonically.
- Record travel, low-energy days, and unusual commitments as constraints for this week's placement.

## 4. Clear the old week

Delete every block in `state/calendar.json` that falls inside the target window, removing both the
calendar event and its state row.

Two exceptions, per the scheduling skill:
- Standing goal blocks that are still valid stay in place. Do not churn them.
- Blocks the user explicitly asked to keep stay in place.

Never delete an event that is not in `state/calendar.json`.

## 5. Budget before placing

Compute available time and total demand per the scheduling skill.

**If demand exceeds available time, stop here.** Report the shortfall in hours and propose explicit
tradeoffs — which tier-2 goal to cut, which task to start a week early, which deliverable to accept
partial credit on. Wait for the user to choose. Do not place blocks against an infeasible plan.

## 6. Place

Place blocks in priority order per the scheduling skill. Tier 1 goals first, then coursework by
priority, then tier 2 goals, then tier 3 into whatever is left.

Create each event on the `Semester` calendar with a plain title, the task ID alone as the
description, no location, no reminders. Add its row to `state/calendar.json` as you go.

## 7. Write the week note

Write `$VAULT/weeks/<YYYY>-W<NN>.md` following `templates/week.md`: the check-in answers, the hour
budget table (per course and per goal, required against scheduled, with available hours), every
placement, any goals cut and what displaced them, and anything at risk.

Add the retro to the *previous* week's note based on what the user reported in step 2.

## 7b. Push the Reminders mirror

Push every open task to Reminders with updated hours and this week's block subdivisions, so the
phone reflects the new plan. One `apply` call, then rewrite `snapshot` in `state/reminders.json` to
match what you pushed.

## 8. Report and commit

Report the short version: hours scheduled, anything cut, anything at risk. Point at the week note
for the detail rather than reprinting it.

Commit the vault: `plan-week: <YYYY>-W<NN>`.
