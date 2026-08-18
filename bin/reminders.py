#!/usr/bin/env python3
"""Batched Apple Reminders bridge.

Every Reminders operation goes through one osascript invocation, because the
first Apple Event of a session costs 20-30s of app wake-up while subsequent
ones cost about a second. Batching turns a sync from minutes into seconds.

  reminders.py dump                 -> JSON of every open reminder, to stdout
  reminders.py apply <plan.json>    -> execute a batch of operations
  reminders.py apply -              -> read the plan from stdin

The plan is {"ops": [...]}, executed in order:

  {"op": "ensure_list", "list": "NAME"}
  {"op": "set_list_style", "list": "NAME", "color": "#0A84FF", "emoji": "\U0001f9e0"}
  {"op": "create", "list": "NAME", "name": "TEXT", "body": "TEXT",
                   "due": "YYYY-MM-DDTHH:MM", "priority": 0, "flagged": false}
  {"op": "update", "id": "x-apple-reminder://...", "name": ..., "body": ...,
                   "due": ... | null}
  {"op": "complete", "id": "x-apple-reminder://..."}
  {"op": "delete",   "id": "x-apple-reminder://..."}

Only `list` and `id` identify targets; nothing is matched by name, so a
renamed reminder is never mistaken for a different one.

This file contains no personal data. List names, task text, and dates all
arrive from the caller.
"""

import json
import subprocess
import sys

FS = "\x1f"   # between fields
RS = "\x1e"   # between records
TIMEOUT = 180


def osascript(source):
    p = subprocess.run(
        ["osascript", "-"], input=source, capture_output=True,
        text=True, timeout=TIMEOUT,
    )
    if p.returncode != 0:
        raise RuntimeError(p.stderr.strip() or "osascript failed")
    return p.stdout


def esc(s):
    """Quote a Python string as an AppleScript string literal.

    AppleScript has no newline escape, so a multi-line value has to be built by
    concatenating with `linefeed`. Emitting a real newline inside the literal
    also lets the generator's own indentation leak into the stored text, which
    silently breaks every later equality check against that text.
    """
    if s is None:
        return '""'
    s = str(s).replace("\\", "\\\\").replace('"', '\\"')
    parts = s.split("\n")
    if len(parts) == 1:
        return '"' + s + '"'
    return " & linefeed & ".join('"' + p + '"' for p in parts)


# --- dump ------------------------------------------------------------------

# Properties are fetched in bulk off the live specifier -- one Apple Event per
# property instead of one per reminder. The specifier must be repeated inline;
# assigning it to a variable first collapses it to a plain list and the bulk
# form stops working.
DUMP = f'''
set FS to (ASCII character 31)
set RS to (ASCII character 30)
set out to ""
tell application "Reminders"
  repeat with l in lists
    set lname to name of l
    set n to count of (reminders in l whose completed is false)
    if n > 0 then
      set ids to id of (reminders in l whose completed is false)
      set nms to name of (reminders in l whose completed is false)
      set bds to body of (reminders in l whose completed is false)
      set dds to due date of (reminders in l whose completed is false)
      set prs to priority of (reminders in l whose completed is false)
      set fls to flagged of (reminders in l whose completed is false)
      repeat with i from 1 to n
        set bd to item i of bds
        if bd is missing value then set bd to ""
        set dd to item i of dds
        if dd is missing value then
          set dpart to ""
        else
          set dpart to ((year of dd) as string) & "-" & ((month of dd as integer) as string) & "-" & ((day of dd) as string) & "-" & ((hours of dd) as string) & "-" & ((minutes of dd) as string)
        end if
        set out to out & lname & FS & (item i of ids) & FS & (item i of nms) & FS & bd & FS & dpart & FS & ((item i of prs) as string) & FS & ((item i of fls) as string) & RS
      end repeat
    end if
  end repeat
end tell
return out
'''


def cmd_dump():
    raw = osascript(DUMP)
    items = []
    for rec in raw.split(RS):
        rec = rec.strip("\n\r")
        if not rec:
            continue
        f = rec.split(FS)
        if len(f) < 7:
            continue
        lst, rid, name, body, dpart, pri, flag = f[:7]
        due = None
        if dpart:
            try:
                y, mo, d, h, mi = (int(x) for x in dpart.split("-"))
                due = f"{y:04d}-{mo:02d}-{d:02d}T{h:02d}:{mi:02d}"
            except ValueError:
                due = None
        items.append({
            "list": lst,
            "id": rid,
            "name": name,
            "body": body,
            "due": due,
            "priority": int(pri) if pri.isdigit() else 0,
            "flagged": flag == "true",
        })
    json.dump({"reminders": items, "count": len(items)},
              sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")


# --- apply -----------------------------------------------------------------

def as_date(iso, var):
    """AppleScript to build a date. Day is set to 1 first so that setting
    month never overflows out of a short month (e.g. Jan 31 -> Feb)."""
    date, _, clock = iso.partition("T")
    y, mo, d = (int(x) for x in date.split("-"))
    h, mi = (int(x) for x in (clock or "00:00").split(":")[:2])
    return (f'set {var} to (current date)\n'
            f'set day of {var} to 1\n'
            f'set year of {var} to {y}\n'
            f'set month of {var} to {mo}\n'
            f'set day of {var} to {d}\n'
            f'set time of {var} to ({h} * hours + {mi} * minutes)\n')


def build(ops):
    """Each op is wrapped in its own try block. A batch is not a transaction:
    without isolation the first failure aborts every op after it, silently
    losing work that had nothing wrong with it."""
    body = []
    warnings = []
    for i, op in enumerate(ops):
        kind = op.get("op")
        v = f"d{i}"
        if kind == "ensure_list":
            body.append(
                f'if not (exists list {esc(op["list"])}) then '
                f'make new list with properties {{name:{esc(op["list"])}}}')
        elif kind == "create":
            props = [f'name:{esc(op["name"])}']
            if op.get("body"):
                props.append(f'body:{esc(op["body"])}')
            if op.get("priority"):
                props.append(f'priority:{int(op["priority"])}')
            if op.get("flagged"):
                props.append("flagged:true")
            pre = ""
            if op.get("due"):
                pre = as_date(op["due"], v)
                props.append(f"due date:{v}")
            body.append(
                pre + f'set nr to make new reminder at end of list '
                f'{esc(op["list"])} with properties {{{", ".join(props)}}}\n'
                f'set news to news & "{i}" & FSEP & (id of nr) & RSEP')
        elif kind == "update":
            tgt = f'(first reminder whose id is {esc(op["id"])})'
            lines = []
            if "name" in op:
                lines.append(f'set name of {tgt} to {esc(op["name"])}')
            if "body" in op:
                lines.append(f'set body of {tgt} to {esc(op["body"])}')
            if "priority" in op:
                lines.append(f'set priority of {tgt} to {int(op["priority"])}')
            if "flagged" in op:
                lines.append(
                    f'set flagged of {tgt} to '
                    f'{"true" if op["flagged"] else "false"}')
            if op.get("due"):
                lines.append(as_date(op["due"], v)
                             + f'set due date of {tgt} to {v}')
            elif "due" in op:
                # Reminders rejects `missing value` for due date (-1700). The
                # only way to clear one is delete + create, which mints a new
                # id, so the caller must ask for that explicitly.
                warnings.append(
                    f'op {i}: cannot clear a due date; delete and recreate '
                    f'the reminder instead')
            body.extend(lines)
        elif kind == "set_list_style":
            tgt = f'list {esc(op["list"])}'
            if op.get("color"):
                body.append(f'set color of {tgt} to {esc(op["color"])}')
            if op.get("emoji"):
                emblem = '{"Emoji" : "' + op["emoji"] + '"}'
                body.append(f'set emblem of {tgt} to {esc(emblem)}')
        elif kind == "complete":
            body.append(
                f'set completed of (first reminder whose id is '
                f'{esc(op["id"])}) to true')
        elif kind == "delete":
            body.append(
                f'delete (first reminder whose id is {esc(op["id"])})')
        else:
            raise ValueError(f"unknown op: {kind!r}")

    blocks = []
    for n, b in enumerate(body):
        inner = "\n".join("    " + ln for ln in b.split("\n"))
        blocks.append(
            f'  try\n{inner}\n  on error e\n'
            f'    set errs to errs & "op {n}: " & e & RSEP\n  end try')
    joined = "\n".join(blocks)
    return (f'set RSEP to (ASCII character 30)\n'
            f'set FSEP to (ASCII character 31)\n'
            f'set GSEP to (ASCII character 29)\n'
            f'set errs to ""\nset news to ""\n'
            f'tell application "Reminders"\n{joined}\nend tell\n'
            f'return errs & GSEP & news\n'), warnings


def cmd_apply(path):
    text = sys.stdin.read() if path == "-" else open(path).read()
    ops = json.loads(text).get("ops", [])
    if not ops:
        print(json.dumps({"applied": 0, "failed": [], "warnings": []}))
        return
    script, warnings = build(ops)
    raw = osascript(script)
    err_part, _, new_part = raw.partition("\x1d")
    failed = [e for e in err_part.split("\x1e") if e.strip()]
    created = {}
    for rec in new_part.split("\x1e"):
        if "\x1f" in rec:
            idx, _, rid = rec.strip("\n\r").partition("\x1f")
            if idx.strip().isdigit():
                created[int(idx)] = rid
    print(json.dumps({"applied": len(ops) - len(failed),
                      "failed": failed, "warnings": warnings,
                      "created": created}, indent=2))


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    try:
        if sys.argv[1] == "dump":
            cmd_dump()
        elif sys.argv[1] == "apply":
            cmd_apply(sys.argv[2] if len(sys.argv) > 2 else "-")
        else:
            sys.exit(__doc__)
    except subprocess.TimeoutExpired:
        sys.exit("error: Reminders did not respond within "
                 f"{TIMEOUT}s. Open Reminders.app and retry.")
    except Exception as e:
        sys.exit(f"error: {e}")


if __name__ == "__main__":
    main()
