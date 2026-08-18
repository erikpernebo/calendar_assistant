---
description: Reconcile Apple Reminders, the vault, and the calendar — pick up anything added or changed, and schedule it.
argument-hint: "[optional: 'check' to report drift without changing anything]"
---

Reconcile the three places work lives. Mode: $ARGUMENTS — `check` means report only, change nothing.

The mechanics are scripted. **Do not hand-roll AppleScript, do not build reminder plans yourself,
and do not diff the three sources by reading them.** Your job is the judgement the scripts cannot
do: estimates for new work, resolving conflicts, and deciding where blocks go.

## 1. Look

```
./bin/sync.py status --vault "$VAULT"
```

One wake-up, one JSON report. Fields: `new_in_reminders`, `completed_or_deleted`,
`due_changed_on_phone`, `due_changed_in_vault`, `conflicts`, `unfiled`, `unscheduled`,
`calendar_drift`, `unknown_lists`.

If `summary.clean` is true, say so in one line and stop — no commit, no calendar writes.

In `check` mode: report and stop here.

## 2. New tasks — `new_in_reminders`

Reminders you added that have no task ID yet. **The list already tells you the course or category —
never ask which one it is.**

Infer type and `context` from the name: laundry is a `home` chore, groceries an `errand`, a problem
set is `campus` coursework, a reading is `anywhere`. Record any problem numbers or counts in `parts`.

Then ask, in **one** batched message, only for what you could not infer — almost always the
estimate, and the deadline when there is no due date. Never invent an estimate for work you know
nothing about.

Write the tasks into `tasks/open.md` with monotonic IDs, each carrying the `reminder_id` from the
report. Step 5 writes the task ID back into the reminder body so it is never re-detected as new.

## 3. Edits — `due_changed_on_phone`, `due_changed_in_vault`, `conflicts`

- **On phone** — pull it in: update `due` in the vault and treat the schedule as stale.
- **In vault** — nothing to do by hand; step 5 pushes it.
- **Conflict** — show `was`, `phone`, and `vault` side by side and ask. Never choose silently.

## 4. Completions — `completed_or_deleted`

The reminder is gone, which means completed **or** deleted and the two are indistinguishable. List
them and confirm before archiving. For confirmed completions set `status: done`, set `spent` (ask if
unknown — actuals are what calibrate future estimates), move the task to `tasks/done.md`, and remove
its calendar blocks.

## 5. Push

```
./bin/sync.py push --vault "$VAULT"                 # add --dry-run to preview
./bin/sync.py push --vault "$VAULT" --notes n.json  # with per-task block lines
```

This builds the plan, applies it in one batch, and rewrites `snapshot` in
`state/reminders.json` — you do not maintain the snapshot by hand.

It is idempotent: an unchanged task plans zero ops. If a second run plans work again, something is
wrong; investigate rather than re-running.

`--notes` takes `{"T-042": "Next block Wed 14:00: problems 4-6"}` to append a line to a body. Use it
after scheduling so the phone shows which slice belongs to the next block.

Read the result:
- **`link`** — reminder ids for newly created reminders. **Write these into `tasks/open.md`
  immediately.** Until you do, those tasks resync as new.
- **`failed`** — report anything that did not land. Never assume success.
- **`skipped`** — tasks whose list is not in `owned_lists`, or whose reminder has vanished. Resolve
  these rather than ignoring them.

## 6. Scheduling — `unscheduled`, `calendar_drift`

Load the `scheduling` skill.

`unscheduled` is work with hours remaining and no calendar block. Schedule what belongs in this
window, respecting each task's `context` — a `home` chore can never go in a between-class gap.
Chores and errands compete for the same hours as coursework; budget them together.

`calendar_drift` is blocks pointing at tasks that no longer exist. Remove them.

If scheduling changed which slice belongs to the next block, re-run `push` with `--notes`.

## 7. Unfiled — `unfiled`, `unknown_lists`

Items in lists the agent does not own, including the default `Reminders` list. **Report them, never
touch them.** Ask whether the list should be added to `owned_lists` in `state/reminders.json`.

## 8. Report and commit

Short diff only: tasks picked up, edits merged and which way, completions archived, blocks added or
moved, anything unfiled or in conflict. Commit the vault: `sync: N in, M scheduled`.
