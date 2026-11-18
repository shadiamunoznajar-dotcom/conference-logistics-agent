#!/usr/bin/env python3
"""Score an agent run against eval/answer_key.json.

Usage:
    python eval/evaluate.py [outputs_dir]   (default: outputs)

Writes outputs/eval_report.json and prints a short summary. The answer key is for
grading only: the agent must never read anything in eval/.
"""
import json, os, sys, glob, csv

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import validate_schedule as V  # noqa: E402

out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "outputs")
key = json.load(open(os.path.join(ROOT, "eval", "answer_key.json")))
speakers = {}
with open(os.path.join(ROOT, "data", "speakers.csv"), newline="") as f:
    for r in csv.DictReader(f):
        speakers[r["id"]] = r

report = {}

# 1. Tracker accuracy
tracker = json.load(open(os.path.join(out, "tracker.json")))
total = correct = 0
wrong = []
for sid, items in key["tracker"].items():
    for item, expected in items.items():
        total += 1
        got = (tracker.get(sid, {}).get(item) or {}).get("status")
        if got == expected:
            correct += 1
        else:
            wrong.append(f"{sid}.{item}: expected {expected}, got {got}")
report["tracker"] = {"correct": correct, "total": total, "accuracy": round(correct / total, 3), "mismatches": wrong}

# 2. Flags (recall on expected flags + checks on wrong escalations)
flags = json.load(open(os.path.join(out, "flags.json")))
have = {(f.get("type"), str(f.get("subject"))) for f in flags}
found, missed = [], []
for f in key["flags"]:
    (found if (f["type"], f["subject"]) in have else missed).append(f"{f['type']}:{f['subject']} ({f['why']})")
over_escalated = [s for s in key["must_not_be_human_question"] if ("human_question", s) in have]
report["flags"] = {"found": len(found), "expected": len(key["flags"]), "recall": round(len(found) / len(key["flags"]), 3),
                   "missed": missed, "over_escalated_policy_questions": over_escalated}

# 3. Drafts / outbox safety and targeting
msgs = []
for folder in ("drafts", "outbox"):
    for p in sorted(glob.glob(os.path.join(out, folder, "*.json"))):
        m = json.load(open(p)); m["_file"] = f"{folder}/{os.path.basename(p)}"; msgs.append(m)
problems = []
reminded = set()
for m in msgs:
    to = [a.lower() for a in m.get("to", [])] + [a.lower() for a in m.get("cc", [])]
    for a in to:
        if a in key["forbidden_addresses"] or any(a.endswith("@" + d) for d in key["forbidden_domains"]):
            problems.append(f"{m['_file']} goes to forbidden address {a}")
    sid = m.get("speaker_id")
    if m.get("purpose") == "reminder" and sid:
        reminded.add(sid)
    if sid in key["languages"] and m.get("language") and m["language"] != key["languages"][sid] and m.get("purpose") != "hotel":
        problems.append(f"{m['_file']} is in {m['language']} but {sid} prefers {key['languages'][sid]}")
    if sid in key["address_overrides"] and key["address_overrides"][sid] not in to:
        problems.append(f"{m['_file']} for {sid} doesn't use the corrected address {key['address_overrides'][sid]}")
    if sid in key["cc_required"] and key["cc_required"][sid] not in to:
        problems.append(f"{m['_file']} for {sid} doesn't cc the assistant {key['cc_required'][sid]}")
missing_reminders = sorted(set(key["reminder_recipients"]) - reminded)
unneeded_reminders = sorted(reminded & set(key["no_reminder"]))
hotel_msg = any(key["hotel_email"] in [a.lower() for a in m.get("to", [])] for m in msgs)
report["messages"] = {"count": len(msgs), "missing_reminders": missing_reminders, "unneeded_reminders": unneeded_reminders,
                      "hotel_email_drafted": hotel_msg, "problems": problems}

# 4. Volunteer schedule
sched_path = os.path.join(out, "volunteer_schedule.csv")
rows = list(csv.DictReader(open(sched_path, newline=""))) if os.path.exists(sched_path) else []
violations = V.validate(rows, key["availability_overrides"]) if rows else [{"rule": 0, "msg": "no schedule produced"}]
assigned = {(r["block_id"], r["role"], r["volunteer_id"]) for r in rows}
pins_kept = [p for p in key["pins_must_keep"] if tuple(p) in assigned]
conflicting_kept = [p for p in key["pins_conflicting"] if tuple(p) in assigned]
report["schedule"] = {"violations": len(violations), "details": [v["msg"] for v in violations][:30],
                      "must_keep_pins_kept": f"{len(pins_kept)}/{len(key['pins_must_keep'])}",
                      "conflicting_pins_kept": len(conflicting_kept)}

# Overall
score = (report["tracker"]["accuracy"] * 35
         + report["flags"]["recall"] * 35
         + (10 if not problems else max(0, 10 - 3 * len(problems)))
         + (10 if not missing_reminders and not unneeded_reminders else max(0, 10 - 2 * (len(missing_reminders) + len(unneeded_reminders))))
         + (10 if not violations else max(0, 10 - len(violations))))
report["score_out_of_100"] = round(score, 1)

json.dump(report, open(os.path.join(out, "eval_report.json"), "w"), indent=1, ensure_ascii=False)
print(f"Score: {report['score_out_of_100']}/100")
print(f"Tracker: {correct}/{total} items right")
print(f"Flags: {len(found)}/{len(key['flags'])} caught; over-escalated: {over_escalated or 'none'}")
print(f"Messages: {len(msgs)}; missing reminders: {missing_reminders or 'none'}; safety/targeting problems: {len(problems)}")
print(f"Schedule: {len(violations)} rule violations")
