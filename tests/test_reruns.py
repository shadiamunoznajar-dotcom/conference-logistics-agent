"""Regression tests for draft retention and recipient-specific timing alerts."""
import unittest
import json
import test_guardrails as fixtures
from agent_tools import AgentTools


class RerunTests(unittest.TestCase):
    setUp = fixtures.GuardrailTests.setUp
    tearDown = fixtures.GuardrailTests.tearDown
    call = fixtures.GuardrailTests.call
    message = fixtures.GuardrailTests.message
    read = fixtures.GuardrailTests.read
    complete_inbox = fixtures.GuardrailTests.complete_inbox

    def test_send_pass_routes_retained_drafts_once_across_restart(self):
        self.engine.mode = 'draft'
        self.complete_inbox()
        first = self.call('write_message', **self.message())
        blocked = self.call('write_message', **self.message('S06', to=['ricardo.paredes@gmial.com']))
        self.assertFalse(blocked['ok'])
        self.call('write_message', **self.message(purpose='other'))
        self.engine = AgentTools(self.root, 'send')
        result = self.engine.dispatch_all()
        self.assertEqual(sum(r['sent'] for r in result), 1)
        self.assertEqual(sum(not r['sent'] for r in result), 1)
        self.assertFalse((self.root / first['path']).exists())
        outbox = self.root / next(r['path'] for r in result if r['sent'])
        original = outbox.read_bytes()
        original_time = outbox.stat().st_mtime_ns
        self.engine = AgentTools(self.root, 'send')
        again = self.engine.dispatch_all()
        self.assertTrue(next(r for r in again if r['sent'])['duplicate_suppressed'])
        self.assertEqual(len(self.engine.state['sent_records']), 1)
        self.assertEqual(outbox.read_bytes(), original)
        self.assertEqual(outbox.stat().st_mtime_ns, original_time)

    def test_post_send_change_gets_new_identity_without_overwriting_original(self):
        self.complete_inbox()
        first = self.call('write_message', **self.message())
        original_path = self.root / first['path']
        original = original_path.read_bytes()
        self.engine.state['tracker']['S01']['arrival']['value'] = 'Updated flight evidence'
        second = self.call('write_message', **self.message(body='Reminder with the updated flight.'))
        self.assertTrue(second['sent'])
        self.assertNotEqual(first['path'], second['path'])
        self.assertNotEqual(first['message_id'], second['message_id'])
        self.assertEqual(second['supersedes'], first['message_id'])
        self.assertEqual(original_path.read_bytes(), original)
        self.assertEqual(len(self.engine.state['sent_records']), 2)
        self.engine.dispatch_all()
        self.assertEqual(len(self.engine.state['sent_records']), 2)

    def test_unchanged_draft_survives_and_rewording_is_ignored(self):
        self.engine.mode = 'draft'
        first = self.call('write_message', **self.message())
        filename = first['path'].split('/')[-1]
        original = (self.root / first['path']).read_bytes()
        self.engine = AgentTools(self.root, 'draft')
        result = self.call('write_message', **self.message(body='Unnecessary rewording.'))
        self.assertTrue(result['retained'])
        self.assertEqual(original, (self.root / first['path']).read_bytes())
        self.assertIn(filename, self.engine.state['messages'])
        self.assertFalse(self.call('remove_draft', file=filename)['ok'])

    def test_changed_facts_allow_replacement_and_removal_is_reported(self):
        self.engine.mode = 'draft'
        first = self.call('write_message', **self.message())
        self.engine.state['tracker']['S01']['arrival']['value'] = 'New flight'
        updated = self.call('write_message', **self.message(body='Changed flight details.'))
        self.assertNotIn('retained', updated)
        self.engine.state['tracker']['S01']['arrival']['value'] = 'Another new flight'
        filename = first['path'].split('/')[-1]
        self.assertEqual(self.call('remove_draft', file=filename)['removed'], filename)
        self.engine.write_summary('Test')
        self.assertIn(filename, (self.root / 'outputs/run_summary.md').read_text(encoding='utf-8'))

    def test_timing_targets_use_moderator_and_actual_session_lead(self):
        self.engine.add_internal_flag('speaker_timing_conflict', 'S03', 'Arrival risks Panel 1', [], True)
        self.engine.state['schedule'] = [dict(block_id='D1-P1', role='lead', volunteer_id='V08')]
        targets = self.engine.timing_targets()
        self.assertIn(('moderator', 'mvillalobos@harvard-example.edu', 'es'),
                      [(t['role'], t['email'], t['language']) for t in targets])
        self.assertIn(('lead', 'sofia.vargas@asah-antara.org', 'es'),
                      [(t['role'], t['email'], t['language']) for t in targets])
        msg = self.message('S03', purpose='heads_up', to=['sofia.vargas@asah-antara.org'], language='en')
        self.assertFalse(self.call('write_message', **msg)['ok'])

    def test_restore_archived_valid_av_draft(self):
        self.engine.mode = 'draft'
        original = self.message('S05', purpose='other', body='Please confirm video playback.')
        original.update(sent=False, run_id=1)
        self.engine.state.setdefault('message_history', []).append(original)
        filename = self.engine.message_name(original)
        self.call('restore_draft', file=filename)
        self.assertEqual(self.engine.state['messages'][filename]['body'], original['body'])
        self.assertIn(filename, self.engine.state['draft_restorations'])
