---
name: scheduling
description: The scheduling policy for the semester planning agent — how to size work blocks, where to place them around existing commitments, how to prioritize when the week is oversubscribed, how to ramp exam prep, how to defend persistent goals against homework creep, and how to recalibrate estimates when work runs long. Load before placing, moving, or removing any calendar block.
---

# Scheduling policy

This is the agent's judgment, written down. Follow it rather than improvising. When a rule genuinely
does not fit the situation, say which rule you are departing from and why.

## The procedure

Every scheduling run — whether `/plan-week` placing a whole week or `/capture` slotting one new
assignment — follows the same five steps in order.

### 1. Establish the window

Determine today's date and the target window. `/plan-week` plans Monday through Sunday of the coming
week. `/capture` and `/adjust` work from now through the end of the current week, extending further
only if a deadline requires it.

### 2. Read busy time

Call `list_events` for **every** calendar in `list_calendars`, across the target window. All of them,
not just the `Semester` calendar — classes, team practices, club meetings, and personal events all
consume real time.

Then subtract, in this order:
- existing calendar events (any calendar), plus travel time if the event has a location across campus
- quiet hours from `semester.md`
- fixed weekly commitments from `semester.md`
- meals and transitions if `semester.md` defines them

What remains is **available time**. Everything downstream fits inside it.

### 3. Compute demand

For each open task, remaining work is `estimate - spent`, multiplied by the course's `estimate_bias`
if the estimate was originally yours rather than the user's.

Sum the remaining work that must happen in this window — anything due inside the window, plus the
share of longer-horizon work (projects, exam ramps) that this window should carry. Add each goal's
weekly hour target from `goals.md`.

### 4. Compare before placing

If demand exceeds available time, **stop and report** before writing anything to the calendar. State
the shortfall in hours and propose explicit tradeoffs. Never resolve it silently by shrinking
estimates, deleting buffer, or scheduling into the night.

### 5. Place, then record

Place blocks in priority order (below). For each event created: write it to the `Semester` calendar,
then immediately add its row to `state/calendar.json`. Never let the two drift apart within a turn.

## Block shape

- **Default 90 minutes.** Range 60–120. Minimum 45 — anything shorter is not worth the context switch.
- **Maximum 3 hours on one task per day.** Beyond that, returns collapse. Spread it across days.
- **15 minutes between adjacent blocks.** Never schedule back-to-back work blocks.
- **Maximum 4 academic blocks per day**, roughly 6 hours of scheduled work. If a day needs more than
  that, the week is oversubscribed — go back to step 4.
- **Round to :00, :15, :30, :45.** No 13:07 start times.
- **Never place a block inside quiet hours**, even for an emergency deadline. Flag it instead.

## Deadline backpressure

- Work must **finish before the deadline with buffer**, not end at it.
  - Tasks of 3 hours or more: last block ends at least a full day before the deadline.
  - Smaller tasks: last block ends the morning of the due date at the latest.
- **Never schedule work in the final 4 hours before a deadline.** That window is for submission
  problems, not for writing code.
- Tasks over 6 hours must span **at least three separate days**. No two-sitting heroics on a large
  assignment.
- If a task cannot fit before its deadline under these rules, it is a shortfall — report it at step
  4. Do not compress the buffer away to make it fit.

## Priority order

When the week is oversubscribed and something must give, rank tasks by:

1. **Nearest deadline** — what is due soonest wins.
2. **Grade weight** — a 20% project outranks a 2% problem set at similar deadlines.
3. **Slip count** — work that has already slipped gets pulled **earlier**, not dropped. A task with
   `slips: 2` is a task the user avoids; scheduling it later guarantees a third slip. Give it a
   morning block, when energy is highest, and make it the first thing that week.
4. **Goal tier** — see below.

Blocked tasks (`status: blocked`) are not scheduled. Surface them in the report so the user can
unblock them.

## Exam ramps

Exams do not get one large cram block. They get a ramp over the preceding 7–10 days, rising in
density:

- Days 10–7 out: one 60–90 minute review block, spaced.
- Days 6–3 out: one block per day, 90 minutes, covering material in order.
- Days 2–1 out: two blocks per day — one recall/practice, one weak-area targeted.
- **Day of the exam**: one short review block at most, ending 2 hours before the exam. Nothing else.

Ramps are created as separate tasks (`type: exam`) so their hours are budgeted like any other work.

## Persistent goals

Goals live in `goals.md` with a weekly hour target and a tier.

- **Tier 1 is immovable.** Place tier 1 goal blocks *before* coursework and route coursework around
  them. If coursework cannot fit around a tier 1 goal, that is a shortfall to report — not a reason
  to cut the goal.
- **Tier 2 is defended but yielding.** Cut a tier 2 block only when a deadline is inside 48 hours and
  no other placement exists. When you cut one, log it in the week note under a "Goals cut" heading
  with the task that displaced it, so the user can see what their coursework actually cost.
- **Tier 3 is opportunistic.** Fill leftover available time, in preference order given in `goals.md`.

Goal blocks are titled by the goal's short name — `Gym`, `Recruiting prep` — with no course code and
no task ID in the description unless the goal has a tracking task.

Recurring goal blocks that already exist and are still valid should be **left in place** across
weekly replans. Do not delete and recreate a standing Tuesday gym block just because the week was
regenerated — churn makes the calendar untrustworthy.

## Handling slips

When the user reports incomplete work:

1. Update `spent` to what they actually did and increment `slips`.
2. Recompute remaining work: `estimate - spent`, applying the course's `estimate_bias`.
3. If the user says the task is bigger than expected, raise `estimate` directly and say so.
4. Reschedule the remaining hours into the rest of the window, subject to every rule above.
5. If the remaining work no longer fits before the deadline, say so immediately. Do not wait for the
   weekly replan to surface it.

A second slip on the same task is a signal, not noise. Move it earlier in the day and earlier in the
week, and consider whether it is actually blocked on something the user has not named.

## Estimate calibration

Each course note carries `estimate_bias`, default `1.0`.

When a task closes with `spent > estimate`, adjust that course's bias toward the observed ratio,
damped so one bad week does not swing it:

```
observed = spent / original_estimate
bias_new = bias_old + 0.3 * (observed - bias_old)
```

Clamp to `[0.7, 2.0]`. Round to two decimals. Apply the bias to estimates **you** generate for that
course. When the user gives an explicit estimate, use their number, but if bias exceeds 1.3, mention
that this course has historically run long.

Never silently rewrite a user-supplied estimate.

## Placement heuristics

Within the rules above, prefer:

- **Hard thinking in the user's stated peak hours** from `semester.md`; routine work (reading,
  problem set cleanup, review) outside them.
- **Blocks adjacent to the relevant class** — work on a course the same day it meets, while it is
  fresh, rather than five days later.
- **Fewer context switches**: two 90-minute blocks on one task beats four 45-minute blocks across
  four tasks on the same day.
- **Morning blocks for avoided work** — anything with `slips > 0`.
- **Friday evening and Saturday left empty** unless a deadline forces it or the user asked otherwise.

## Reporting

After any scheduling run, report a **short diff**, not the full week:

- what was added, with day and time
- what moved, and from where
- what was cut or squeezed, and what displaced it
- what is now at risk — deadlines with no slack left

Follow with the hour budget table: per course and per goal, hours scheduled against hours targeted
or required. Keep it to what changed and what is in danger.
