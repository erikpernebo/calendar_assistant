---
description: Propose meeting times for an external scheduling request, ranked by what each one costs, and hold them until the other party replies.
argument-hint: "<paste the email, or: 30 min call next week, recruiter in London>"
---

Find meeting times for: $ARGUMENTS

This command **never writes to the calendar**. It writes holds and nothing else. Booking is
`/book`.

## 1. Read the request

Extract from the text, and state what you extracted so the user can correct it:

- **duration** (default 30 minutes)
- **window** — "this week and next" resolves against today's date from `date`. Default: tomorrow
  through 14 days out.
- **the other party's time zone** — take a named zone at face value (`BST` -> `Europe/London`).
  Convert it yourself; never ask the user to.
- **medium** — a video call needs somewhere private to talk. A phone call is more forgiving. An
  in-person meeting needs travel time and a `campus`/`errand` context.
- **anything else the email asks for.** Scheduling requests usually carry a second question. Surface
  it at the end of your report so it does not get lost. Do not answer it.

## 2. Build the busy list

Read `$VAULT/semester.md` for classes, fixed commitments, meals, sleep, and commute. Read
`$VAULT/goals.md` for defended time.

Call `list_calendars`, then `list_events` on **every** calendar across the window.

Assemble one busy list. Every entry needs a `cost` — what it costs the user to give it up — and a
`flex_min` if it can shift instead. `semester.md` annotates each commitment with both; use those
values rather than judging for yourself. Events read off a calendar that `semester.md` does not
describe take the cost of their calendar, given in the calendar table there.

Also add as busy:

- **The agent's own work blocks**, from `$VAULT/state/calendar.json`. Cost `free`, and carry the
  `event_id` and `task_id` through so `/book` can re-place them.
- **Active holds**, from `$VAULT/state/holds.json` — slots already offered to someone else and not
  yet resolved. Cost `high`. Offering the same slot to two people is the one unrecoverable failure
  here.
- **Sleep and wind-down** are not busy entries; they are the edges of `day_windows`.

## 3. Rank

Run `bin/freetime.py`, giving it the request on stdin. Its docstring defines the request shape.

Set `day_windows` from the sleep table, starting each day **45 minutes after wake time** — nobody
should take a recruiter call fifteen minutes after getting out of bed — and ending at wind-down.

Set `pad_before_min: 15` and `pad_after_min: 15`. The first is finding somewhere to talk and
connecting; the second is overrun plus getting to whatever is next. On a day with back-to-back
campus obligations, raise the trailing pad rather than trusting a five-minute gap.

Do not re-rank its output by feel. If you disagree with the ordering, the costs in `semester.md` are
wrong — fix those and re-run, so the next request benefits too.

## 4. Report

Offer **three to five** slots, on distinct days. For each:

```
Tue 25 Aug   11:45-12:15 ET   (16:45-17:15 BST)   free
Wed 26 Aug   11:15-11:45 ET   (16:15-16:45 BST)   misses COURSE-CODE lecture
```

State the cost of any slot that has one, in plain words — "misses your COURSE-CODE lecture", "you would
skip the club social", "displaces 90 minutes of COURSE-CODE work, which re-fits Thursday evening".
A slot with a cost is still worth offering; an unstated cost is not.

Then give a **paste-ready block** for the reply: plain lines, both time zones, no markdown, no
emoji, day and date spelled out. Nothing else — the user writes their own email.

If every candidate scores above `OUTSIDE_COUNTERPARTY`, there is no mutually workable time. Say that
plainly, show the least-bad options, and name what would unlock a good one — an earlier start, a
missed recitation, the other party taking a call outside their hours.

## 5. Hold

Append every offered slot to `$VAULT/state/holds.json`:

```json
{"holds": [
  {"hold_id": "H-004", "label": "recruiter call", "start": "...", "end": "...",
   "created": "2026-08-18", "expires": "2026-08-23", "status": "offered",
   "group": "H-004"}
]}
```

All slots offered for one request share a `group`, so `/book` can release the rest in one move.
Default expiry is 5 days; a hold past its expiry is inactive and stops blocking time. Never delete
an expired hold silently — report it at the next `/status` so the user knows an offer went stale.

Commit the vault: `find-time: <label>, N slots held`.
