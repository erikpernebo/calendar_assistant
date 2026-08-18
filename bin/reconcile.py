#!/usr/bin/env python3
"""Three-way reconciliation between the vault, Apple Reminders, and the calendar.

Answers one question: what changed since the last sync, and who changed it?

Without a record of what was last pushed you cannot tell a deadline the user
moved on their phone from one the agent set itself, so a naive "vault wins"
rule silently discards the user's edits. `state/reminders.json` is that record.

  reconcile.py --vault /path/to/vault [--dump cached.json]

Emits JSON. Every finding is a fact, never an action -- the agent decides what
to do, this only reports drift.
"""

import argparse
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TASK_RE = re.compile(r"^###\s+(T-\d+)\s*(.*)$")
FIELD_RE = re.compile(r"^-\s*([a-z_]+)\s*:\s*(.*?)\s*$")


def parse_tasks(path):
    """Parse tasks/open.md into dicts. Ignores fenced code blocks so the
    field-reference example in the file header is not read as a real task."""
    tasks, cur, fenced = [], None, False
    if not os.path.exists(path):
        return tasks
    for line in open(path, encoding="utf-8"):
        line = line.rstrip("\n")
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if fenced:
            continue
        m = TASK_RE.match(line)
        if m:
            title = m.group(2).strip().lstrip("\u00b7").strip()
            cur = {"id": m.group(1), "title": title, "fields": {}}
            tasks.append(cur)
            continue
        if cur:
            f = FIELD_RE.match(line)
            if f:
                cur["fields"][f.group(1)] = f.group(2)
    return tasks


def hours(v):
    if not v:
        return 0.0
    m = re.match(r"^\s*([\d.]+)\s*h", str(v))
    return float(m.group(1)) if m else 0.0


def load(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return default


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", required=True)
    ap.add_argument("--dump", help="cached reminders.py dump, to avoid a second call")
    a = ap.parse_args()

    v = a.vault
    if a.dump:
        dump = json.load(open(a.dump, encoding="utf-8"))
    else:
        r = subprocess.run([os.path.join(HERE, "reminders.py"), "dump"],
                           capture_output=True, text=True)
        if r.returncode != 0:
            sys.exit(r.stderr.strip() or "dump failed")
        dump = json.loads(r.stdout)

    cfg = load(os.path.join(v, "state", "reminders.json"),
               {"snapshot": {}, "owned_lists": [], "protected_lists": []})
    snap = cfg.get("snapshot", {})           # task_id -> last pushed state
    owned = set(cfg.get("owned_lists", []))
    protected = set(cfg.get("protected_lists", []))

    tasks = parse_tasks(os.path.join(v, "tasks", "open.md"))
    by_rid = {t["fields"].get("reminder_id"): t
              for t in tasks if t["fields"].get("reminder_id")}

    rem = [r for r in dump["reminders"] if r["list"] not in protected]
    live_ids = {r["id"] for r in rem}

    out = {
        "new_in_reminders": [],
        "completed_or_deleted": [],
        "due_changed_on_phone": [],
        "due_changed_in_vault": [],
        "conflicts": [],
        "unfiled": [],
        "unscheduled": [],
        "calendar_drift": [],
        "unknown_lists": [],
    }

    for r in rem:
        linked = re.search(r"\bT-\d+\b", r.get("body") or "")
        if linked:
            continue
        entry = {"id": r["id"], "list": r["list"], "name": r["name"],
                 "due": r["due"], "body": r["body"]}
        if r["list"] in owned:
            out["new_in_reminders"].append(entry)
        else:
            # somewhere the agent does not manage -- surface, never auto-file
            out["unfiled"].append(entry)
            if r["list"] not in out["unknown_lists"]:
                out["unknown_lists"].append(r["list"])

    for t in tasks:
        f = t["fields"]
        rid = f.get("reminder_id")
        if not rid:
            continue
        if rid not in live_ids:
            out["completed_or_deleted"].append(
                {"task": t["id"], "title": t["title"], "reminder_id": rid,
                 "note": "completed or deleted on the phone -- indistinguishable, confirm"})
            continue
        live = next(r for r in rem if r["id"] == rid)
        was = snap.get(t["id"], {})
        vault_due = (f.get("due") or "").replace(" ", "T")[:16] or None
        phone_due = live["due"]
        base_due = was.get("due")
        phone_moved = base_due is not None and phone_due != base_due
        vault_moved = base_due is not None and vault_due != base_due
        rec = {"task": t["id"], "title": t["title"], "reminder_id": rid,
               "was": base_due, "phone": phone_due, "vault": vault_due}
        if phone_moved and vault_moved and phone_due != vault_due:
            out["conflicts"].append(rec)
        elif phone_moved:
            out["due_changed_on_phone"].append(rec)
        elif vault_moved or (base_due is None and vault_due != phone_due):
            out["due_changed_in_vault"].append(rec)

    # tasks with work left but no calendar block. A task already reported as
    # completed on the phone is not "unscheduled" -- listing it in both places
    # would have the agent scheduling work it is about to archive.
    cal = load(os.path.join(v, "state", "calendar.json"), {"blocks": []})
    scheduled = {b.get("task_id") for b in cal.get("blocks", [])}
    gone = {x["task"] for x in out["completed_or_deleted"]}
    for t in tasks:
        f = t["fields"]
        if f.get("status") in ("done", "blocked") or t["id"] in gone:
            continue
        left = hours(f.get("estimate")) - hours(f.get("spent"))
        if left > 0 and t["id"] not in scheduled:
            out["unscheduled"].append(
                {"task": t["id"], "title": t["title"], "hours_left": round(left, 2),
                 "due": f.get("due"), "context": f.get("context")})

    known = {t["id"] for t in tasks}
    for b in cal.get("blocks", []):
        if b.get("task_id") not in known:
            out["calendar_drift"].append(
                {"event_id": b.get("event_id"), "task_id": b.get("task_id"),
                 "note": "block references a task that is no longer open"})

    out["summary"] = {k: len(vv) for k, vv in out.items() if isinstance(vv, list)}
    out["summary"]["clean"] = not any(
        out[k] for k in out if isinstance(out[k], list))
    json.dump(out, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
