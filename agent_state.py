"""Atomic authoritative state, with the spec's output files as readable mirrors."""
import csv
import hashlib
import json
import os
import tempfile
from pathlib import Path

ITEMS = ('bio', 'headshot', 'dietary', 'breakfast_rsvp', 'av_needs', 'arrival', 'receipts', 'slides')


def digest(value):
    if not isinstance(value, bytes):
        value = json.dumps(value, sort_keys=True, ensure_ascii=False).encode('utf-8')
    return hashlib.sha256(value).hexdigest()


def atomic_text(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.' + path.name, suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='') as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def atomic_json(path, value):
    atomic_text(path, json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def read_csv(path):
    with open(path, encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))


def initial_tracker(speakers):
    result = {}
    for sid, speaker in speakers.items():
        entries = {}
        for item in ITEMS:
            status, value = 'missing', None
            if (item == 'receipts' and speaker['travel_category'] != 'B'
                    or item == 'arrival' and speaker['travel_category'] == 'L'
                    or item == 'slides' and speaker['slides_expected'] != 'yes'):
                status = 'not_required'
            if item == 'arrival' and speaker['travel_category'] == 'A':
                status, value = 'received', speaker['arrival']
            entries[item] = dict(status=status, value=value, source='data/speakers.csv; data/policies.md')
        result[sid] = entries
    return result


class State:
    def __init__(self, output, speakers, mode):
        self.output = Path(output)
        path = self.output / 'state.json'
        self.data = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {
            'version': 1, 'processed_emails': {}, 'pending_emails': {},
            'tracker': initial_tracker(speakers), 'flags': [], 'contacts': {},
            'proxies': {}, 'bounced': [], 'quarantined': [], 'overrides': {},
            'messages': {}, 'sent_fingerprints': [], 'read_sources': [],
            'schedule': [], 'reports': {}, 'validated_hash': None,
            'step': 0, 'run_id': 0,
        }
        self.data.update(mode=mode, run_id=self.data['run_id'] + 1,
                         run_calls=0, validation_calls=0, status='running')
        self.save()

    def save(self):
        # state.json is the single source of truth. A crash while publishing mirrors
        # is repaired on startup; no recovery journal or multi-file transaction.
        atomic_json(self.output / 'state.json', self.data)
        for filename, key in [('tracker.json', 'tracker'), ('flags.json', 'flags'),
                              ('availability_overrides.json', 'overrides')]:
            atomic_json(self.output / filename, self.data[key])
