---
description: Add a new assignment, exam, project, or deadline, and schedule it if it needs work this week.
argument-hint: "<course code> <what it is> <when it is due> [rough estimate]"
---

Capture new work: $ARGUMENTS

## 1. Parse

Extract the course code, task name, type, due date and time, and any estimate the user gave. Resolve
relative dates ("next Thursday") against today's date from `date`.

If the course code does not match a note in `$VAULT/courses/`, ask before creating anything — it may
be a typo, or the course may need `/add-course` first.

If the due date is genuinely ambiguous, ask. Do not guess a deadline.

## 2. Estimate

If the user gave an estimate, use their number. If they did not, derive one from the course note's
`typical assignment size` and similar past tasks in `$VAULT/tasks/done.md`, then multiply by that
course's `estimate_bias`. State the estimate you chose and where it came from, so the user can
correct it.

If the course's `estimate_bias` is above 1.3 and the user supplied their own estimate, mention that
this course has historically run long — but use their number.

## 3. Record

Allocate the next task ID by scanning `$VAULT/tasks/open.md` and `$VAULT/tasks/done.md` for the
highest existing `T-NNN`. Append a task entry to `$VAULT/tasks/open.md` in the format defined in
CLAUDE.md, with `[[COURSE-CODE]]` as a wikilink, `spent: 0h`, `status: not-started`, `slips: 0`.

If the user mentioned a grade weight, record it. Otherwise look it up in the course note's grading
table.

## 4. Schedule if needed

Load the `scheduling` skill.

Decide whether this task needs work inside the current week. It does if its deadline falls in this
week, or if the buffer rules mean work must start now to finish on time.

If it does: read busy time across all calendars, place the blocks per the scheduling policy, create
the events on the `Semester` calendar, and update `$VAULT/state/calendar.json`.

If placing this work requires moving or removing existing blocks, do it — but only blocks recorded
in `state/calendar.json` — and report every move.

If it does not need work this week, say so and note when work should start.

## 5. Report and commit

Report a short diff: the task you created, the estimate and its source, blocks added with day and
time, anything that moved to make room, and anything now at risk.

Commit the vault: `capture: T-NNN <short name>`.
