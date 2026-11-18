# Volunteer schedule rules

The agent builds `volunteer_schedule.csv` from `conference.json` (the roles each block needs), `volunteers.csv` (who is available and what they can do), `pinned_assignments.csv` (requests from the team) and any availability changes found in the inbox.

1. **Every slot is filled.** Each role in each block gets exactly the number of people listed in `count`.
2. **One named person per slot.** No "X or Y", no "X and Y", no "Volunteer 1", no "TBD".
3. **Skills.** `it` needs `av`; `mc` and `host` need `bilingual`; `lead` needs `lead`; `catering_lead` needs `catering`. Other roles need no skill.
4. **Availability.** A person can only work inside their availability windows (after applying any changes from the inbox).
5. **Escort timing.** An escort starts 30 minutes before the session (speaker call time) and stays until the session ends. Panel 1 escort: 3:40–5:10 PM, for example.
6. **No double booking.** A person can't hold two assignments whose times overlap, including the escort's extra 30 minutes.
7. **Rest.** No one works more than **3 hours in a row**. A gap of at least 30 minutes resets the count.
8. **Spread the load.** Nobody should have more than 5 assignments across the whole conference.
9. **Pinned assignments** are kept unless they break a rule. If they do, the agent does not silently drop them: it keeps the most important one, lists the conflict in `human_review.md`, and explains its proposed fix.

`tools/validate_schedule.py` checks rules 1–8 and reports violations. The agent should run it, fix what it reports, and run it again until it's clean.
