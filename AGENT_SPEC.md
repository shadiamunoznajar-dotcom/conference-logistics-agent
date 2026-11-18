# Build spec: Conference Logistics Agent

This is the engineering spec for the agent. `prompts/system_prompt.md` is what the model reads; this file is what the code must do.

## Definition
"An LLM agent runs tools in a loop to achieve a goal." (Simon Willison)
- **Goal:** get every speaker and volunteer ready for the conference: track what's missing, chase it, answer what the policies allow, escalate the rest, and produce a run-of-show and a valid volunteer schedule.
- **Tools:** read the inbox and data files, update a tracker, raise flags, draft or send emails, set volunteer availability changes, save and validate the volunteer schedule, write reports.
- **Loop:** the model picks the next tool call based on what it learned from the last one, until it calls `finish` (or hits the step limit).
- **Evaluate:** `eval/evaluate.py` scores a run against a hand-built answer key (tracker accuracy, flags caught, message safety and targeting, schedule rule violations).

## Stack
- Python 3.10+, no web framework needed.
- OpenAI API with function calling (Responses or Chat Completions). Model from env var `OPENAI_MODEL` (default a current GPT model that supports tools). Key from `OPENAI_API_KEY` in a `.env` file that is git-ignored. **Never commit the key.**
- Dependencies in `requirements.txt` (openai, python-dotenv). Nothing else unless needed.

## Command line
```
python agent.py                 # draft mode (default): nothing is "sent"
python agent.py --mode send     # allowed messages go to outputs/outbox/ instead of drafts/
python agent.py --fresh         # wipe outputs/ and state, start over
python eval/evaluate.py         # score the latest run
```
A second run without `--fresh` only processes emails it hasn't seen yet (tracked in `outputs/state.json`), then redoes the downstream steps (reminders, hotel email, schedule, reports) so they reflect the new information. This is the live demo: drop `data/demo/027.txt` into `data/inbox/` and run again.

## Tools to implement (function calling)
All tools return JSON. Every call is appended to `outputs/agent_log.jsonl` as `{"step", "time", "tool", "args", "result_summary", "note"}` where `note` is a one-line reason the model gives (add a required `reason` string argument to every tool for this). The viewer page uses this log as the replay.

| Tool | Args | Does |
|---|---|---|
| `list_inbox` | — | Unprocessed email files, sorted by Date header, with From/Subject/Date/Attachments. |
| `read_email` | `file` | Full email text. Marks it processed in state. |
| `read_data_file` | `path` | Any file under `data/` except `data/demo/`. Refuses `eval/` and anything outside `data/`. |
| `get_tracker` | `speaker_id?` | Current tracker (one speaker or all). |
| `update_tracker` | `speaker_id, item, status, value, source` | `item` ∈ bio, headshot, dietary, breakfast_rsvp, av_needs, arrival, receipts, slides. `status` ∈ received, missing, partial, not_required. Also `update_contact(speaker_id, email)` for address changes. |
| `add_flag` | `type, subject, summary, sources, needs_human` | Appends to `outputs/flags.json`. Types listed in the system prompt. |
| `resolve_flag` | `flag_id, resolution` | Marks a flag handled (e.g. "answered in reminder draft"). |
| `write_message` | `to[], cc[], speaker_id?, language, purpose, subject, body` | `purpose` ∈ reminder, answer, hotel, heads_up, other. Saves to `outputs/drafts/NN_<slug>.json`. In send mode, if the send rules below pass, saves to `outputs/outbox/` instead and returns `sent: true`; otherwise returns why it stayed a draft. |
| `set_availability_override` | `volunteer_id, availability, source` | Saves to `outputs/availability_overrides.json`. |
| `save_schedule` | `rows[]` (`block_id, role, volunteer_id`) | Writes `outputs/volunteer_schedule.csv`. |
| `validate_schedule` | — | Runs `tools/validate_schedule.py` on the saved schedule with the overrides; returns violations. |
| `write_report` | `name, markdown` | `name` ∈ run_of_show, human_review, breakfast. Writes `outputs/<name>.md`. |
| `finish` | `summary` | Ends the run, writes `outputs/run_summary.md`. |

### Code-level guardrails (enforced in Python, not just the prompt)
- `write_message` refuses any address that bounced (seen in a bounce email and recorded with a `bounced_email` flag), any domain not in: speakers' domains, the hotel's, the organizer's. It reports the refusal back to the model.
- Send mode only sends when: purpose is `reminder` or `answer`, every `to` address matches speakers.csv (or a contact update the human approved, which never happens inside a run), and the speaker has no open flag with `needs_human: true`.
- `read_data_file` can't read `eval/`.
- Max 200 tool calls per run; max 10 `validate_schedule` calls.
- Deterministic file names so runs can be compared.

## Outputs (`outputs/`)
| File | Content |
|---|---|
| `tracker.json` | `{ "S01": { "bio": {"status","value","source"}, ... }, ... }` |
| `flags.json` | list of `{id, type, subject, summary, sources, needs_human, resolved, resolution}` |
| `drafts/*.json`, `outbox/*.json` | messages as above |
| `availability_overrides.json` | `{ "V06": "Fri 09:00-12:00; ..." }` |
| `volunteer_schedule.csv` | `block_id, role, volunteer_id` |
| `run_of_show.md` | per block: time, title, venue, speakers with arrival/call time, volunteers by role, AV notes, risks |
| `human_review.md` | decisions for the team, each with context and options |
| `breakfast.md` | headcount, names, dietary needs, conflicts |
| `agent_log.jsonl` | every step, for the viewer |
| `run_summary.md` | what the agent did, counts, what's still open |
| `state.json` | processed emails, step count, mode |

## Agent loop (suggested order; the model decides the details)
1. Read conference.json, speakers.csv, policies.md, schedule_rules.md, the sent emails.
2. Initialize the tracker: everything `missing` except what the category makes `not_required` (local speakers don't need arrival; only category B needs receipts; slides required only for keynotes until a panelist says they'll present) and what's already known (category A arrivals come from the booking).
3. Process the inbox oldest first; after each email, follow knock-on effects.
4. Draft reminders, answers, the hotel email and heads-ups.
5. Build, validate and fix the volunteer schedule.
6. Write run_of_show, breakfast, human_review.
7. Self-check, then `finish`.

## Viewer page (built after the first good run)
A single static HTML page (`viewer/index.html`) that loads the JSON/CSV/MD files from a run and shows: the tracker as a color-coded grid, the drafts, the human-review list, the run-of-show, the volunteer schedule, the eval score, and a step-by-step replay of `agent_log.jsonl`. No API key needed; hostable on GitHub Pages or as a Claude artifact.
