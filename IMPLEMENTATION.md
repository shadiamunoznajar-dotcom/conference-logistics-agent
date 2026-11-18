# Running on Windows

From PowerShell in this project folder:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
# Only create .env if it does not already exist:
if (!(Test-Path .env)) { Copy-Item .env.example .env }
notepad .env
.\.venv\Scripts\python.exe -X utf8 -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -X utf8 agent.py --fresh
```

The key must be in the project `.env`; never paste it into chat or commit it.
`OPENAI_MODEL` is configurable, defaulting to `gpt-6.2-sol`.
No external mail service is connected. `--mode send` writes eligible messages to
`outputs/outbox/` only. Hotel messages always stay drafts.

For the live demo:

```powershell
Copy-Item data\demo\027.txt data\inbox\027.txt
.\.venv\Scripts\python.exe -X utf8 agent.py
```

The runtime cannot read `data/demo/` or `eval/`. Evaluation is a separate human step.
The existing validator is called unchanged using `-X utf8`.

## Persistence and replay

`state.json` is the authoritative atomic checkpoint, including tracker, flags,
contacts, pending/processed email fingerprints, messages and counters. Required
JSON/CSV/Markdown files are mirrors. `read_email` marks pending;
`checkpoint_email` commits after the model records facts. Pending work is re-read
after a crash; stable flags and message names make replays idempotent. There is no
separate recovery journal. Every attempted function call has a JSONL log entry,
including its required one-line reason and any refusal. A crash at the exact moment
of appending a log can still leave incomplete replay history; state remains atomic.

`--fresh` deletes only the verified project outputs folder. Ordinary runs retain
state and rebuild downstream drafts. An unchanged previously sent message is not
sent twice. Outbox files are simulated artifacts, so a later blocker can move them
back to drafts; this is not a real email recall.

## Approved guardrails

- Exact source-backed corrected contacts may receive drafts only. No tool can
  approve a contact, change mode, or resolve `needs_human` flags.
- Both To and CC obey bounce/domain checks. Speaker messages target their named
  speaker; proxy CCs must be recorded from that speaker's correspondence.
- Sending requires all inbox checkpoints, an original roster address, permitted
  purpose, correct language, and no open human decision for the speaker.
- `policy_refs` is nullable; answers require exact excerpts from policies.md.
  Combined reminder/answer messages must also provide references. Excerpt checking
  confirms provenance, not complete semantic correctness of generated prose.
- Explicit instruction attacks are quarantined, cannot supply mutation evidence,
  and generate suspicious_email flags. Pattern detection is defense in depth, not
  a complete prompt-injection classifier; the tool sandbox remains the boundary.
- V01 keeps registration lead and welcome MC; another volunteer escorts Panel 1.
- No completion without current clean validation and all required reports.

Schema definitions are in `agent_tools.TOOLS`. `checkpoint_email` is the added tool
for the approved pending/completed workflow. `policy_refs` is the approved extra
write_message field. `value` is a string or null; merged evidence uses semicolon-
separated source paths. Availability overrides replace the full weekly windows.

An interrupted process can leave `.agent.lock`. Verify no agent process is running
before removing that file. Exit 0 means completed; exit 1 means failed or incomplete,
with a sanitized error in `outputs/run_summary.md` when state initialization succeeded.
