# Conference Logistics Agent

An AI agent that does the part of organizing a conference nobody wants to do: reading every speaker's reply, keeping track of who still owes a bio or a flight receipt, noticing when a changed flight breaks the hotel booking or the speaker breakfast, drafting the reminders, and building the volunteer schedule.

Built for DPI-681 (The Science and Implications of Generative AI, Harvard Kennedy School), Assignment 2, Level 4: build and evaluate an agent.

## Why
Running a two-day student conference means hundreds of emails in two languages, each with a small piece of information that changes something else. A speaker's flight moves, so the hotel dates change, early check-in has to be requested, and they can no longer make the breakfast they RSVP'd to. A volunteer has an exam, so Saturday's schedule has a hole. These are easy to miss by hand and expensive when missed.

## The demo conference
Everything here is fictional. The **Antara Conference at Harvard 2027** is about the República de Antara, an invented Andean, Spanish-speaking country (capital Kallpa). The data is modeled on the kinds of emails a real student conference receives, but every person, address and institution is made up.

- 12 speakers in four travel situations (flight booked by the team / reimbursed / self-funded / local), Spanish and English
- 16 volunteers with availability windows and skills
- 19 blocks over three days, each needing specific roles
- 26 inbox emails: replies, follow-ups that correct earlier replies, an assistant writing on a speaker's behalf, a bounced address, a hotel rooming list with mistakes, a volunteer dropping out, empty "received" replies, and one email that tries to give the agent instructions

## What the agent produces
- A tracker of what every speaker has sent and what's missing
- Reminder drafts in each speaker's language, which also answer questions the policies cover
- One email to the hotel with every change it needs
- A list of decisions for a human, with context and options
- A run-of-show and a volunteer schedule that passes all the rules
- A step-by-step log of every tool call, for the viewer page

Draft mode is the default. Send mode only "sends" messages that are safe to send without a human (see `AGENT_SPEC.md`).

## Run it
```
pip install -r requirements.txt
echo "OPENAI_API_KEY=sk-..." > .env
python agent.py --fresh
python eval/evaluate.py
```
Live demo: copy `data/demo/027.txt` into `data/inbox/` and run `python agent.py` again. A speaker's flight is cancelled the night before; watch what changes.

## How it's evaluated
`eval/answer_key.json` lists, by hand, the correct status of all 96 speaker items, the 22 problems the agent should catch, who should and shouldn't get a reminder, and the schedule constraints. `eval/evaluate.py` scores a run on tracker accuracy, flags caught, message safety (no emails to bounced or outside addresses, right language, right recipients) and schedule rule violations. The agent never sees the answer key.

## Latest run
`outputs/` holds the final run: the 26 emails plus the demo flight change, run in send mode. Five reminders went to the (simulated) outbox and eleven messages stayed drafts, each held for a stated rule. All 59 volunteer slots are filled with zero rule violations. Score: 91.5/100 (`outputs/eval_report.json`).

To see it without running anything, open `viewer/index.html` in a browser. It shows the tracker, the decisions left for a person, every message, the schedule, and a step-by-step replay of all 311 tool calls.

## Repo map
```
agent.py, ...            the agent (built with Codex)
prompts/system_prompt.md what the model is told
AGENT_SPEC.md            tools, outputs, guardrails
CODEX_PROMPT.md          how this was built with Codex
data/                    the fictional conference + inbox
tools/validate_schedule.py  schedule rule checker (agent tool + grader)
eval/                    answer key + evaluator (agent can't read)
outputs/                 latest run
viewer/                  results viewer page
```
