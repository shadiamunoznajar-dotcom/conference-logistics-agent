"""Security decisions are local Python decisions, never model permissions."""
import re
import unicodedata
from email.utils import parseaddr
from pathlib import Path


class Refusal(ValueError):
    pass


def confined(root, relative, excluded=()):
    root = Path(root).resolve()
    raw = Path(relative)
    if raw.is_absolute() or raw.drive or ':' in str(relative):
        raise Refusal('Only relative paths are allowed.')
    path = (root / raw).resolve()
    if not path.is_relative_to(root) or path == root:
        raise Refusal('Path escapes the allowed directory.')
    if any(part.casefold() in excluded for part in path.relative_to(root).parts):
        raise Refusal('This directory is not accessible.')
    return path


def address(value):
    if not isinstance(value, str) or any(c in value for c in '\r\n,;'):
        raise Refusal('Use one plain email address per recipient.')
    parsed = parseaddr(value)[1].lower()
    if parsed != value.strip().lower() or not re.fullmatch(r"[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-z0-9-]+(?:\.[a-z0-9-]+)+", parsed):
        raise Refusal('Invalid plain email address.')
    return parsed


def normalize(text):
    return ''.join(c for c in unicodedata.normalize('NFKD', text.casefold())
                   if not unicodedata.combining(c))


def identifies(text, speaker):
    words = [w for w in re.findall(r'\w+', normalize(speaker['name']))
             if len(w) > 2 and w not in {'prof', 'dra', 'dr'}]
    body = normalize(text)
    return sum(bool(re.search(r'\b' + re.escape(w) + r'\b', body)) for w in words) >= 2


def suspicious(text):
    # Conservative quarantine for explicit attempts to control the agent. This is
    # defense in depth, not a claim to recognize every possible prompt injection.
    return bool(re.search(
        r'note to the ai|ignore (?:all |your |previous |prior )*instructions|'
        r'switch to send mode|mark every speaker as complete|'
        r'do not include this step in your report|system prompt|developer message',
        text, re.I))


def validate_recipients(message, speakers, conference, state):
    if not message['to']:
        raise Refusal('At least one To recipient is required.')
    domains = {address(s['email']).split('@')[1] for s in speakers.values()}
    domains |= {address(conference['organizer_email']).split('@')[1],
                address(conference['hotel']['reservations_email']).split('@')[1]}
    sid = message.get('speaker_id')
    proposed = state['contacts'].get(sid, {}).get('email')
    for kind in ('to', 'cc'):
        message[kind] = [address(a) for a in message[kind]]
        for recipient in message[kind]:
            if recipient in state['bounced']:
                raise Refusal('A recipient is on the persistent bounced-address denylist.')
            if recipient.split('@')[1] not in domains:
                # Exact correction exception is only for the speaker's To field.
                if kind != 'to' or recipient != proposed:
                    raise Refusal('A recipient domain is not allowed.')
    if message['purpose'] in ('reminder', 'answer'):
        if sid not in speakers:
            raise Refusal('Speaker messages require a known speaker_id.')
        targets = {address(speakers[sid]['email']), proposed}
        if any(a not in targets for a in message['to']):
            raise Refusal('Speaker messages may only address their named speaker.')
        if any(a not in state['proxies'].get(sid, []) for a in message['cc']):
            raise Refusal('Proxy CC must be recorded from this speaker correspondence.')
        if message['language'] != speakers[sid]['language']:
            raise Refusal('Message language differs from the speaker preference.')
    if message['purpose'] == 'hotel':
        if message['to'] != [address(conference['hotel']['reservations_email'])] or message['language'] != 'en':
            raise Refusal('Hotel changes require one English message to the hotel.')


def send_blocks(message, speakers, state, inbox_complete):
    reasons = []
    sid = message.get('speaker_id')
    if not inbox_complete:
        reasons.append('Inbox processing is incomplete.')
    if message['purpose'] not in ('reminder', 'answer'):
        reasons.append('Only reminders and policy answers may be sent.')
    if sid not in speakers or message['to'] != [address(speakers[sid]['email'])]:
        reasons.append('Recipient is not the original approved speaker address.')
    if any(f['subject'] == sid and f['needs_human'] and not f['resolved'] for f in state['flags']):
        reasons.append('Speaker has an open human decision.')
    return reasons


def check_policy_refs(refs, policies, purpose):
    refs = refs or []
    if purpose == 'answer' and not refs:
        raise Refusal('Policy answers require policy_refs.')
    for reference in refs:
        if not isinstance(reference, str) or not reference.strip() or reference.strip() not in policies:
            raise Refusal('Every policy_ref must be an exact excerpt present in data/policies.md.')


def validate_schema(value, schema):
    types = schema.get('type', [])
    types = [types] if isinstance(types, str) else types
    actual = ('null' if value is None else 'boolean' if isinstance(value, bool)
              else 'object' if isinstance(value, dict) else 'array' if isinstance(value, list)
              else 'string' if isinstance(value, str) else 'number')
    if actual not in types:
        raise Refusal('Tool argument type does not match its schema.')
    if 'enum' in schema and value not in schema['enum']:
        raise Refusal('Unknown tool argument value.')
    if actual == 'object':
        if set(value) != set(schema['required']):
            raise Refusal('Missing or unexpected tool arguments.')
        for key, item in value.items():
            validate_schema(item, schema['properties'][key])
    if actual == 'array':
        for item in value:
            validate_schema(item, schema['items'])
