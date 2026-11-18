#!/usr/bin/env python3
"""Check a volunteer schedule against data/schedule_rules.md.

Usage:
    python tools/validate_schedule.py outputs/volunteer_schedule.csv [--overrides outputs/availability_overrides.json]

The schedule CSV needs the columns: block_id, role, volunteer_id
The optional overrides file replaces a volunteer's availability, e.g.
    {"V06": "Fri 09:00-12:00; Fri 15:00-21:00; Sat 12:00-14:00"}

Prints a JSON report and exits with code 0 if the schedule is clean, 1 otherwise.
The agent can call this as a tool; the evaluator uses it too.
"""
import csv, json, sys, argparse, os
from datetime import datetime, timedelta
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DAYS = {"Thu": "2027-04-15", "Fri": "2027-04-16", "Sat": "2027-04-17"}
SKILL_FOR_ROLE = {"it": "av", "mc": "bilingual", "host": "bilingual", "lead": "lead", "catering_lead": "catering"}
MAX_CONTINUOUS = timedelta(hours=3)
REST_GAP = timedelta(minutes=30)
MAX_ASSIGNMENTS = 5
ESCORT_LEAD = timedelta(minutes=30)


def ts(s):
    return datetime.fromisoformat(s)


def parse_windows(text):
    out = []
    for part in text.split(";"):
        part = part.strip()
        if not part:
            continue
        day, span = part.split(" ", 1)
        a, b = span.split("-")
        out.append((ts(f"{DAYS[day]}T{a.strip()}"), ts(f"{DAYS[day]}T{b.strip()}")))
    return out


def load(overrides=None):
    conf = json.load(open(os.path.join(ROOT, "data", "conference.json")))
    blocks = {b["id"]: b for b in conf["blocks"]}
    vols = {}
    with open(os.path.join(ROOT, "data", "volunteers.csv"), newline="") as f:
        for r in csv.DictReader(f):
            vols[r["id"]] = {"name": r["name"], "skills": set(s.strip() for s in r["skills"].split(";") if s.strip()),
                             "windows": parse_windows(r["availability"])}
    for vid, text in (overrides or {}).items():
        if vid in vols:
            vols[vid]["windows"] = parse_windows(text)
    return blocks, vols


def window_for(block, role):
    start, end = ts(block["start"]), ts(block["end"])
    if role == "escort":
        start -= ESCORT_LEAD
    return start, end


def validate(rows, overrides=None):
    blocks, vols = load(overrides)
    v = []  # violations
    filled = defaultdict(int)
    per_person = defaultdict(list)

    for i, r in enumerate(rows, start=2):
        b, role, vid = r.get("block_id", "").strip(), r.get("role", "").strip(), r.get("volunteer_id", "").strip()
        if b not in blocks:
            v.append({"rule": 1, "row": i, "msg": f"unknown block '{b}'"}); continue
        needed = {x["role"]: x for x in blocks[b]["roles"]}
        if role not in needed:
            v.append({"rule": 1, "row": i, "msg": f"role '{role}' is not needed in {b}"}); continue
        if vid not in vols:
            v.append({"rule": 2, "row": i, "msg": f"'{vid}' is not a single known volunteer id (no 'X or Y', 'TBD', names)"}); continue
        filled[(b, role)] += 1
        skill = SKILL_FOR_ROLE.get(role)
        if skill and skill not in vols[vid]["skills"]:
            v.append({"rule": 3, "row": i, "msg": f"{vid} ({vols[vid]['name']}) lacks skill '{skill}' for {role} in {b}"})
        s, e = window_for(blocks[b], role)
        if not any(ws <= s and e <= we for ws, we in vols[vid]["windows"]):
            v.append({"rule": 4, "row": i, "msg": f"{vid} ({vols[vid]['name']}) not available {s:%a %H:%M}-{e:%H:%M} for {role} in {b}"})
        per_person[vid].append((s, e, b, role))

    for b, blk in blocks.items():
        for x in blk["roles"]:
            got = filled[(b, x["role"])]
            if got != x["count"]:
                v.append({"rule": 1, "msg": f"{b} needs {x['count']} x {x['role']}, has {got}"})

    for vid, items in per_person.items():
        items.sort()
        for a in range(len(items)):
            for c in range(a + 1, len(items)):
                if items[c][0] < items[a][1] and items[a][0] < items[c][1]:
                    v.append({"rule": 6, "msg": f"{vid} ({vols[vid]['name']}) double booked: {items[a][2]}/{items[a][3]} and {items[c][2]}/{items[c][3]}"})
        # continuous work
        run_start, run_end = None, None
        for s, e, b, role in items:
            if run_start is None or s - run_end >= REST_GAP:
                run_start, run_end = s, e
            else:
                run_end = max(run_end, e)
            if run_end - run_start > MAX_CONTINUOUS:
                v.append({"rule": 7, "msg": f"{vid} ({vols[vid]['name']}) works {run_start:%a %H:%M}-{run_end:%H:%M} without a 30-min break"})
                run_start = None
        if len(items) > MAX_ASSIGNMENTS:
            v.append({"rule": 8, "msg": f"{vid} ({vols[vid]['name']}) has {len(items)} assignments (max {MAX_ASSIGNMENTS})"})

    # de-duplicate messages
    seen, out = set(), []
    for x in v:
        if x["msg"] not in seen:
            seen.add(x["msg"]); out.append(x)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("schedule")
    ap.add_argument("--overrides")
    a = ap.parse_args()
    overrides = json.load(open(a.overrides)) if a.overrides else None
    with open(a.schedule, newline="") as f:
        rows = list(csv.DictReader(f))
    violations = validate(rows, overrides)
    print(json.dumps({"clean": not violations, "violation_count": len(violations), "violations": violations}, indent=1, ensure_ascii=False))
    sys.exit(0 if not violations else 1)


if __name__ == "__main__":
    main()
