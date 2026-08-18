---
description: Ingest a syllabus into a course note plus one task per deadline.
argument-hint: "<course code> [path to syllabus PDF, a URL, or pasted text]"
---

Set up a course: $ARGUMENTS

## 1. Get the source

If the user gave a PDF path, read it. If a URL, fetch it. If pasted text, use that. If they gave
only a course code, ask for the syllabus — a PDF path, a link, or pasted text — before continuing.

## 2. Extract

Pull out, and say explicitly which of these you could not find:

- course code, full name, units, instructor
- lecture, recitation, and office hour times and locations
- the grading breakdown, as component and percentage
- **every dated deliverable**: assignments, problem sets, projects, quizzes, midterms, the final
- late policy and any drop policy (lowest homework dropped, etc.)
- links: course site, Canvas, Gradescope

Syllabus dates are often relative ("Week 4") or partial ("Sept 12" with no year). Resolve them
against the term dates in `$VAULT/semester.md` and today's date from `date`. Where the syllabus
gives a date but no time, ask for the course's usual deadline time once and apply it to all of them
rather than asking per assignment.

## 3. Write the course note

Write `$VAULT/courses/<CODE>.md` following `templates/course.md`, with YAML frontmatter carrying
`code`, `name`, `units`, `instructor`, and `estimate_bias: 1.0`.

Fill the workload notes from what the syllabus says about expected hours. If it says nothing, ask
the user for a rough per-assignment estimate — this is what every future estimate for the course
anchors on, so it is worth one question.

## 4. Create tasks

Append one task entry to `$VAULT/tasks/open.md` for every dated deliverable, IDs allocated
monotonically. For each:

- `type` from the deliverable kind
- `due` as resolved above
- `estimate` from the course's typical assignment size, scaled by the deliverable's grade weight —
  a 15% project is not the same size as a 3% problem set
- `weight` from the grading table
- `spent: 0h`, `status: not-started`, `slips: 0`
- `[[<CODE>]]` wikilink in the heading

For exams, also create the ramp as described in the scheduling skill — a separate `type: exam` task
whose estimate covers the full review load, so its hours get budgeted.

## 5. Do not schedule

**Create no calendar events in this command.** Syllabus ingestion loads a whole semester of
deadlines; scheduling them here would flood the calendar. The user runs `/plan-week` when they are
ready.

## 6. Report and commit

Report: the course note written, the number of tasks created, total estimated hours for the
semester, the heaviest weeks by deadline density, and anything you could not extract and need from
the user.

Commit the vault: `add-course: <CODE>`.
