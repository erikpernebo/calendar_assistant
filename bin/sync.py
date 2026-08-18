#!/usr/bin/env python3
"""One entry point for the Reminders half of a sync.

Everything mechanical lives here so it is not re-derived by hand each week:
taking a snapshot, diffing three sources, generating the push plan, applying
it, and recording what was pushed. What is left for judgement -- estimates for
new work, resolving conflicts, deciding where blocks go -- stays out of it.

  sync.py status --vault V              dump + reconcile in one wake-up
  sync.py push   --vault V [--dry-run]  push the vault out to Reminders
  sync.py push   --vault V --notes n.json   ...with per-task block lines

`push` writes `state/reminders.json`. It never edits `tasks/open.md`; new
reminder ids come back in `link` for the caller to record.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from reconcile import parse_tasks, hours, load          # noqa: E402

WIKILINK = re.compile(r"\[\[([^\]]+)\]\]")


def run(args, **kw):
    p = subprocess.run(args, capture_output=True, text=True, **kw)
    if p.returncode != 0:
        sys.exit(p.stderr.strip() or f"{args[0]} failed")
    return p.stdout


def dump_to_file(path=None):
    out = run([os.path.join(HERE, "reminders.py"), "dump"])
    path = path or tempfile.NamedTemporaryFile(
        suffix=".json", delete=False, mode="w").name
    with open(path, "w", encoding="utf-8") as f:
        f.write(out)
    return path, json.loads(out)


def statefile(v):
    return os.path.join(v, "state", "reminders.json")


def cmd_status(a):
    path, _ = dump_to_file()
    sys.stdout.write(run([os.path.join(HERE, "reconcile.py"),
                          "--vault", a.vault, "--dump", path]))
    if not a.keep:
        os.unlink(path)


def body_for(task, left, notes):
    f = task["fields"]
    line2 = f'est {f.get("estimate", "?")} | {left:g}h left'
    if f.get("context"):
        line2 += f' | context: {f["context"]}'
    lines = [task["id"], line2]
    if f.get("parts"):
        lines.append(f'parts: {f["parts"]}')
    extra = notes.get(task["id"])
    if extra:
        lines.append(extra)
    return "\n".join(lines)


def name_for(task):
    name = WIKILINK.sub("", task["title"]).strip(" ·-").strip()
    parts = task["fields"].get("parts")
    return f"{name} ({parts})" if parts else name


def cmd_push(a):
    v = a.vault
    cfg = load(statefile(v), {"snapshot": {}, "owned_lists": [],
                              "protected_lists": []})
    owned = set(cfg.get("owned_lists", []))
    snap = dict(cfg.get("snapshot", {}))
    notes = load(a.notes, {}) if a.notes else {}

    _, dump = dump_to_file(a.dump) if not a.dump else (
        a.dump, json.load(open(a.dump, encoding="utf-8")))
    live = {r["id"]: r for r in dump["reminders"]}

    tasks = [t for t in parse_tasks(os.path.join(v, "tasks", "open.md"))
             if t["fields"].get("status") != "done"]

    ops, plan_meta, skipped = [], [], []
    for t in tasks:
        f = t["fields"]
        m = WIKILINK.search(t["title"])
        lst = m.group(1) if m else None
        if lst not in owned:
            skipped.append({"task": t["id"], "list": lst,
                            "why": "list is not in owned_lists"})
            continue
        left = hours(f.get("estimate")) - hours(f.get("spent"))
        want = {"name": name_for(t), "body": body_for(t, left, notes),
                "due": (f.get("due") or "").replace(" ", "T")[:16] or None}
        rid = f.get("reminder_id")

        if rid and rid in live:
            cur = live[rid]
            changed = {k: want[k] for k in ("name", "body")
                       if cur.get(k) != want[k]}
            # a due date cannot be cleared once set, so only push a real value
            if want["due"] and cur.get("due") != want["due"]:
                changed["due"] = want["due"]
            if changed:
                ops.append({"op": "update", "id": rid, **changed})
                plan_meta.append({"task": t["id"], "action": "update",
                                  "fields": sorted(changed)})
        elif not rid:
            ops.append({"op": "create", "list": lst, **{
                k: val for k, val in want.items() if val is not None}})
            plan_meta.append({"task": t["id"], "action": "create",
                              "list": lst, "op_index": len(ops) - 1})
        else:
            skipped.append({"task": t["id"], "reminder_id": rid,
                            "why": "reminder missing -- completed or deleted; "
                                   "resolve before pushing"})
            continue
        snap[t["id"]] = {"due": want["due"], "name": want["name"],
                         "list": lst, "reminder_id": rid}

    result = {"planned": len(ops), "plan": plan_meta, "skipped": skipped}

    if a.dry_run:
        result["ops"] = ops
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return

    link = {}
    if ops:
        out = json.loads(run([os.path.join(HERE, "reminders.py"), "apply", "-"],
                             input=json.dumps({"ops": ops})))
        result.update(applied=out["applied"], failed=out["failed"],
                      warnings=out["warnings"])
        for meta in plan_meta:
            if meta["action"] == "create":
                new = out["created"].get(str(meta["op_index"]))
                if new:
                    link[meta["task"]] = new
                    snap[meta["task"]]["reminder_id"] = new
        if out["failed"]:
            result["note"] = ("some ops failed; snapshot still written for the "
                              "ops that succeeded -- rerun status to confirm")

    cfg["snapshot"] = snap
    os.makedirs(os.path.dirname(statefile(v)), exist_ok=True)
    with open(statefile(v), "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
        f.write("\n")

    result["link"] = link
    if link:
        result["next"] = ("record these reminder_id values in tasks/open.md; "
                          "until you do they resync as new")
    print(json.dumps(result, indent=2, ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("status"); s.add_argument("--vault", required=True)
    s.add_argument("--keep", action="store_true", help="keep the dump file")
    s.set_defaults(fn=cmd_status)
    p = sub.add_parser("push"); p.add_argument("--vault", required=True)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--dump", help="reuse an existing dump instead of waking Reminders")
    p.add_argument("--notes", help="JSON of task_id -> extra body line")
    p.set_defaults(fn=cmd_push)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
