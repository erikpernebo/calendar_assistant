#!/usr/bin/env python3
"""Find meeting slots in a calendar, ranked by what they cost to take.

Interval arithmetic across a dozen calendars and two weeks is where hand
reasoning quietly goes wrong -- a missed overlap, a half-hour drift, a
daylight-saving edge. This does that part deterministically and leaves the
judgment (which slots to actually offer, how to phrase them) to the caller.

  freetime.py < request.json        request on stdin, ranked slots on stdout
  freetime.py request.json          or from a file

Nothing here is specific to one person. Commitments, costs, and windows all
arrive in the request; this file contains no personal data.

REQUEST
-------
{
  "tz": "America/New_York",              // the user's zone
  "window": {"start": "2026-08-24T00:00", "end": "2026-09-04T23:59"},
  "duration_min": 30,
  "pad_before_min": 15,                  // finding somewhere to talk, connecting
  "pad_after_min": 10,                   // calls run over
  "granularity_min": 15,
  "max_results": 8,
  "max_per_day": 2,

  "day_windows": [                       // when the user is awake and available
    {"days": [0,1,2,3,4], "start": "09:45", "end": "22:15"}
  ],

  "counterparty": {                      // optional; omit for a solo booking
    "tz": "Europe/London",
    "start": "09:00", "end": "17:30",
    "days": [0,1,2,3,4]
  },

  "busy": [
    {"start": "2026-08-25T09:30", "end": "2026-08-25T10:50",
     "label": "COURSE-CODE lecture",
     "cost": "high",                     // never | high | medium | low | free
     "flex_min": 0,                      // how far it may shift to clear a slot
     "event_id": "...", "task_id": "T-042"}
  ]
}

`days` are Python weekdays: Monday 0 ... Sunday 6.

COST
----
What it costs to take a slot that collides with this commitment.

  never   sleep, meals that are a medical constraint, exams. Excluded outright.
  high    lectures, a recitation the user teaches, chapter meeting.
  medium  a recitation the user attends, a club event.
  low     goal blocks, a meal that can shift.
  free    the agent's own work blocks, which it can re-place.

A commitment with `flex_min` is first tried as a shift: if moving it that far
in either direction clears the slot without hitting anything else, the slot
costs `low` and the shift is reported instead of a miss.

RESPONSE
--------
{"slots": [...], "considered": N, "rejected": {...}}

Each slot carries `start`/`end`, the same times in the counterparty's zone,
`displaces` (what it collides with and at what cost), `notes`, and `score`
-- lower is better. A slot that displaces nothing scores 0.
"""

import json
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# Score added per displaced commitment. The gaps are wide on purpose: no number
# of free work blocks should ever outrank missing one lecture.
COST = {"free": 1, "low": 10, "medium": 40, "high": 100}
NEVER = "never"

# Commitments you cannot be inside of at all. The padding either side of a call
# is only checked against these: you can be finishing lunch or walking to a room
# while you dial in, but you cannot be in a lecture.
HARD = {NEVER, "high", "medium"}

OUTSIDE_COUNTERPARTY = 300   # they cannot make it; worth surfacing, not offering first
WEEKEND = 25
ODD_START = 3                # :15 and :45 look arbitrary in an email
FRAGMENT = 15                # per useless stub left in a displaced block
STUB_MIN = 45                # shorter than this is not worth a context switch

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def parse(s, tz):
    """Accept naive local time or anything datetime.fromisoformat handles."""
    d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    return d.replace(tzinfo=tz) if d.tzinfo is None else d.astimezone(tz)


def hhmm(s):
    h, _, m = s.partition(":")
    return int(h) * 60 + int(m or 0)


def overlaps(a1, a2, b1, b2):
    return a1 < b2 and b1 < a2


def day_bounds(day, spec, tz):
    """The [start, end) the given day_window spec carves out of `day`."""
    base = datetime(day.year, day.month, day.day, tzinfo=tz)
    return (base + timedelta(minutes=hhmm(spec["start"])),
            base + timedelta(minutes=hhmm(spec["end"])))


def can_shift(item, s, e, others, tz):
    """Can this commitment move aside far enough to clear [s, e)?

    Returns the shift in minutes, or None. Tries the smaller move first so a
    lunch slides 30 minutes rather than 45 when either would do.
    """
    flex = item.get("flex_min") or 0
    if not flex:
        return None
    dur = item["_end"] - item["_start"]
    # Move late enough to start after the slot, or early enough to end before it.
    for delta in sorted(
        [int((e - item["_start"]).total_seconds() // 60),
         -int((item["_end"] - s).total_seconds() // 60)],
        key=abs,
    ):
        if delta == 0 or abs(delta) > flex:
            continue
        ns = item["_start"] + timedelta(minutes=delta)
        ne = ns + dur
        if overlaps(ns, ne, s, e):
            continue
        if any(o is not item and o.get("cost") != "free"
               and overlaps(ns, ne, o["_start"], o["_end"]) for o in others):
            continue
        return delta
    return None


def counterparty_window(cp, day, tz):
    """The counterparty's working day, expressed in the user's zone.

    Their day is anchored in their own zone, so a slot near midnight can belong
    to their previous or next weekday. Both neighbours are checked.
    """
    if not cp:
        return None
    theirs = ZoneInfo(cp["tz"])
    allowed = set(cp.get("days", [0, 1, 2, 3, 4]))
    spans = []
    for off in (-1, 0, 1):
        d = (day + timedelta(days=off)).astimezone(theirs).date()
        if d.weekday() not in allowed:
            continue
        base = datetime(d.year, d.month, d.day, tzinfo=theirs)
        spans.append((
            (base + timedelta(minutes=hhmm(cp["start"]))).astimezone(tz),
            (base + timedelta(minutes=hhmm(cp["end"]))).astimezone(tz),
        ))
    return spans


def run(req):
    tz = ZoneInfo(req.get("tz", "America/New_York"))
    dur = timedelta(minutes=req.get("duration_min", 30))
    pad_b = timedelta(minutes=req.get("pad_before_min", 15))
    pad_a = timedelta(minutes=req.get("pad_after_min", 10))
    step = timedelta(minutes=req.get("granularity_min", 15))

    w0 = parse(req["window"]["start"], tz)
    w1 = parse(req["window"]["end"], tz)

    busy = []
    for b in req.get("busy", []):
        b = dict(b)
        b["_start"] = parse(b["start"], tz)
        b["_end"] = parse(b["end"], tz)
        busy.append(b)

    cp = req.get("counterparty")
    candidates = []
    rejected = {"never": 0, "outside_day": 0, "no_window": 0}
    considered = 0

    day = datetime(w0.year, w0.month, w0.day, tzinfo=tz)
    while day <= w1:
        wins = [day_bounds(day, s, tz) for s in req.get("day_windows", [])
                if day.weekday() in set(s.get("days", range(7)))]
        cps = counterparty_window(cp, day, tz)
        for win_start, win_end in wins:
            t = win_start
            # Round up to the granularity grid.
            mins = t.hour * 60 + t.minute
            if mins % req.get("granularity_min", 15):
                t += timedelta(minutes=req.get("granularity_min", 15)
                               - mins % req.get("granularity_min", 15))
            while t + dur <= win_end and t < w1:
                s, e = t, t + dur
                if s < w0:
                    t += step
                    continue
                span_s, span_e = s - pad_b, e + pad_a
                if span_s < win_start or span_e > win_end:
                    t += step
                    rejected["outside_day"] += 1
                    continue
                considered += 1

                # Hard commitments are tested against the padded span, soft
                # ones only against the call itself.
                hits = []
                for b in busy:
                    iv = ((span_s, span_e) if b.get("cost", "free") in HARD
                          else (s, e))
                    if overlaps(iv[0], iv[1], b["_start"], b["_end"]):
                        b["_iv"] = iv
                        hits.append(b)
                if any(b.get("cost") == NEVER for b in hits):
                    rejected["never"] += 1
                    t += step
                    continue

                score = 0
                displaces = []
                notes = []
                for b in hits:
                    shift = can_shift(b, b["_iv"][0], b["_iv"][1], busy, tz)
                    if shift is not None:
                        score += COST["low"]
                        displaces.append({"label": b.get("label", "?"),
                                          "cost": "low", "action": "shift",
                                          "shift_min": shift})
                        notes.append(
                            f'{b.get("label","?")} shifts '
                            f'{"later" if shift > 0 else "earlier"} by '
                            f'{abs(shift)} min')
                        continue
                    c = b.get("cost", "free")
                    score += COST.get(c, 1)
                    entry = {"label": b.get("label", "?"), "cost": c,
                             "action": "displace"}
                    for k in ("event_id", "task_id"):
                        if b.get(k):
                            entry[k] = b[k]
                    if c == "free":
                        before = (b["_iv"][0] - b["_start"]).total_seconds() / 60
                        after = (b["_end"] - b["_iv"][1]).total_seconds() / 60
                        stubs = sum(1 for x in (before, after) if 0 < x < STUB_MIN)
                        if stubs:
                            score += FRAGMENT * stubs
                            entry["fragments"] = True
                    else:
                        notes.append(f'misses {b.get("label","?")}')
                    displaces.append(entry)

                in_cp = cps is None or any(
                    c0 <= span_s and span_e <= c1 for c0, c1 in (cps or []))
                if cps is not None and not in_cp:
                    score += OUTSIDE_COUNTERPARTY
                    notes.append("outside the other party's working hours")
                if day.weekday() >= 5:
                    score += WEEKEND
                if s.minute % 30:
                    score += ODD_START

                slot = {
                    "start": s.isoformat(), "end": e.isoformat(),
                    "day": DAYS[s.weekday()],
                    "local": f'{DAYS[s.weekday()]} {s:%d %b} '
                             f'{s:%H:%M}-{e:%H:%M} {s:%Z}',
                    "score": score,
                    "displaces": displaces,
                    "notes": notes,
                    "within_counterparty_hours": bool(in_cp),
                }
                if cp:
                    theirs = ZoneInfo(cp["tz"])
                    ts, te = s.astimezone(theirs), e.astimezone(theirs)
                    slot["counterparty"] = (f'{DAYS[ts.weekday()]} {ts:%d %b} '
                                            f'{ts:%H:%M}-{te:%H:%M} {ts:%Z}')
                candidates.append(slot)
                t += step
        day += timedelta(days=1)

    if not req.get("day_windows"):
        rejected["no_window"] = 1

    # Best first, then spread: a recruiter wants distinct days, not four
    # variations on Tuesday morning.
    candidates.sort(key=lambda c: (c["score"], c["start"]))
    per_day, out = {}, []
    for c in candidates:
        d = c["start"][:10]
        if per_day.get(d, 0) >= req.get("max_per_day", 2):
            continue
        # Keep offers from touching each other.
        if any(o["start"][:10] == d
               and abs((datetime.fromisoformat(o["start"])
                        - datetime.fromisoformat(c["start"])).total_seconds())
               < 3600 for o in out):
            continue
        per_day[d] = per_day.get(d, 0) + 1
        out.append(c)
        if len(out) >= req.get("max_results", 8):
            break

    return {"slots": out, "considered": considered, "rejected": rejected}


def main():
    src = sys.stdin if len(sys.argv) < 2 or sys.argv[1] == "-" else open(sys.argv[1])
    try:
        req = json.load(src)
    except json.JSONDecodeError as ex:
        sys.exit(f"error: request is not valid JSON: {ex}")
    try:
        json.dump(run(req), sys.stdout, indent=2)
    except KeyError as ex:
        sys.exit(f"error: request is missing {ex}")
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
