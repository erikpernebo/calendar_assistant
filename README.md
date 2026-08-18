# calendar_assistant

A semester planning agent for Claude Code. Turns assignments, exams, and persistent goals into work
blocks on Google Calendar, with memory in an Obsidian vault.

## What this is

An agent defined in markdown, not an application. There is no code here to run.

| Piece | What it is |
|---|---|
| Runtime | Claude Code |
| Actuator | Google Calendar connector |
| Memory | A private Obsidian vault |
| The agent | This repo — operating contract, scheduling policy, five commands, a state schema |

The repo holds judgment and structure. It holds no personal data. Courses, deadlines, goals, and
schedules live in a separate private vault whose path is set in a gitignored local config, so
nothing about a real semester ever reaches this repository.

## Commands

| Command | What it does |
|---|---|
| `/sync` | Reconciles Reminders, the vault, and the calendar; picks up whatever changed |
| `/add-course` | Ingests a syllabus into a course note plus one task per deadline |
| `/capture` | Adds one new assignment or exam, and schedules it if it needs work this week |
| `/plan-week` | The weekly rewrite — check in, reconcile, rebudget, reschedule |
| `/adjust` | Mid-week correction — a slip, a moved deadline, a lost day |
| `/status` | Read-only: what is due, what is behind, goals against target |

## Scripts

The mechanical half is code, not prompting — the model handles judgement, the scripts handle
everything repeatable.

| Script | Does |
|---|---|
| `bin/reminders.py` | Batched Apple Reminders bridge: `dump` and `apply`. Every operation goes through one `osascript` call, because the first Apple Event costs 20-30s of app wake-up while later ones cost ~1s. Ops are individually isolated so one failure cannot abort the batch. |
| `bin/reconcile.py` | Three-way diff across Reminders, the vault, and the calendar. Reports facts only — new items, completions, due-date drift, conflicts, unscheduled work, calendar drift. Takes no actions. |
| `bin/sync.py` | The driver. `status` = dump + reconcile in one wake-up. `push` = generate the plan, apply it, rewrite the snapshot. Idempotent: an unchanged task plans zero ops. |

Reminders **Sections and tags are not scriptable** — the dictionary exposes only `account`, `list`,
and `reminder`, and a `#hashtag` written into a name stays literal text. Grouping is therefore done
with real lists, viewed through the built-in `All` smart list.

## How it works

`/plan-week` runs weekly. It asks what finished, what slipped and by how much, what is new, and what
is unusual about the coming week. It reconciles the task list, computes available hours against
required hours, and — only if the week is feasible — places blocks on a dedicated `Semester`
calendar.

`/adjust` runs whenever reality diverges. Report that a four-hour homework only got two hours in,
and it updates the record, recomputes the remainder, and moves the rest of the week around it.

A `state/reminders.json` snapshot records what was last pushed. Without it there is no way to tell a
deadline the user moved on their phone from one the agent set, and a naive "vault wins" rule would
silently discard the user's edits. Phone-only changes are pulled, vault-only changes are pushed, and
anything changed on both sides is surfaced as a conflict rather than resolved silently.

Four ideas do most of the work:

- **Slips get scheduled earlier, not later.** A task the user keeps avoiding gets a morning block at
  the front of the week, on the theory that pushing it back guarantees another slip.
- **Estimates self-calibrate.** Each course carries an `estimate_bias`. When work runs long, the bias
  rises and future estimates for that course scale with it.
- **Location is a hard constraint.** Every task carries a context — `campus`, `home`, `errand`,
  `anywhere`. A `home` chore never lands in a between-class gap, and the scheduler will not send
  someone home and back for a 40-minute round trip.
- **Goals are defended.** Persistent commitments have tiers. Tier 1 is immovable and coursework routes
  around it; tier 2 yields only inside 48 hours of a deadline, and every cut is logged so the cost of
  a heavy week is visible.

When required hours exceed available hours, the agent stops and reports the shortfall rather than
compressing estimates to make the week appear to fit.

## Safety model

Two boundaries, enforced in `CLAUDE.md`:

**Calendar.** Events are created only on a calendar named `Semester`. `update_event` and
`delete_event` are permitted only for events that are both on that calendar and recorded in the
vault's `state/calendar.json`. Every other calendar — personal, university, club — is read-only busy
time. The agent reads them to know when you are unavailable and never writes to them.

**Privacy.** No course names, deadlines, grades, or goals are written anywhere in this repo.
Templates use placeholders. Every data write goes to the vault.

`delete_event` is deliberately left in `ask` rather than `allow` in `.claude/settings.json`, so
deletions surface a prompt. A weekly replan clears the previous week's blocks, so expect a handful
of prompts during `/plan-week`. Move it to `allow` if that becomes tiresome and you trust the guard.

## Setup

1. Install Obsidian and create a vault. Keep it outside this repo.
2. Make the vault a **private** git repo. Its history is the undo button.
3. Create a Google calendar named exactly `Semester`. The connector can create events but not
   calendars, so this step is manual.
4. Create `vault.local.json` in this repo (gitignored):
   ```json
   {"vault": "/absolute/path/to/vault"}
   ```
5. Create `.claude/settings.local.json` (gitignored) granting access to the vault:
   ```json
   {"permissions": {"additionalDirectories": ["/absolute/path/to/vault"]}}
   ```
6. Scaffold the vault from `templates/`: `semester.md`, `goals.md`, `courses/`, `tasks/open.md`,
   `tasks/done.md`, `weeks/`, `log/`, `state/calendar.json`.
7. Add a shell alias so the vault is always in scope:
   ```bash
   alias sem='cd /path/to/calendar_assistant && claude --add-dir /path/to/vault'
   ```
8. Run `/add-course` for each class, fill in `semester.md` and `goals.md`, then `/plan-week`.

## Vault layout

```
semester.md          term dates, breaks, fixed commitments, quiet hours, work style
goals.md             persistent goals: weekly hour targets and priority tiers
courses/<CODE>.md    one note per course; frontmatter carries estimate_bias
tasks/open.md        every open task, one "### T-NNN" section each
tasks/done.md        archive
weeks/YYYY-Www.md    budget table, placements, reasoning, retro
log/YYYY-MM-DD.md    daily notes appended by /adjust
state/calendar.json  event_id -> task_id for every block the agent owns
```
