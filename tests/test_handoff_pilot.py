"""Exercise the Spec-only pilot without a model, network, credentials, or chat messages."""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

MODULE = Path(__file__).resolve().parents[1] / 'tools/handoff_pilot.py'
spec = importlib.util.spec_from_file_location('handoff_pilot', MODULE)
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)

FAKE = '''#!/usr/bin/env python3
import json,sys,time
from pathlib import Path
if sys.argv[1:]==['login','status']:
 print('Logged in using ChatGPT');sys.exit(0)
if '--version' in sys.argv:
 print('codex-cli fake-test-only');sys.exit(0)
if '--help' in sys.argv:
 print('--json --sandbox --ignore-user-config --output-last-message');sys.exit(0)
assert sys.argv[sys.argv.index('--sandbox')+1]=='read-only'
assert '--ignore-user-config' in sys.argv
payload=sys.stdin.read()
output=Path(sys.argv[sys.argv.index('--output-last-message')+1])
(output.parent/'started').write_text('yes')
if 'SLOW_TEST' in payload:time.sleep(30)
if 'FAIL_TEST' in payload:sys.exit(9)
output.write_text('# Sample Spec\\nAwaiting version approval.')
if 'UNKNOWN_USAGE_TEST' not in payload:
 print(json.dumps({'type':'turn.completed','usage':{'input_tokens':120,'cached_input_tokens':100,'output_tokens':20,'reasoning_output_tokens':8}}))
'''


class PilotTests(unittest.TestCase):
    def setUp(self):
        clean_env = patch.dict(os.environ, {k:v for k,v in os.environ.items() if k not in ['CODEX_API_KEY','OPENAI_API_KEY']}, clear=True)
        clean_env.start()
        self.addCleanup(clean_env.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / 'repo'
        self.repo.mkdir()
        subprocess.run(['git','init','--quiet',str(self.repo)],check=True)
        subprocess.run(['git','-C',str(self.repo),'remote','add','origin','https://github.com/kwinweng/shiguang-hot.git'],check=True)
        self.pilot = bridge.Pilot(self.root / 'private')
        self.pilot.init(self.repo, 'group-test')
        self.fake = self.root / 'fake-codex'
        self.fake.write_text(FAKE)
        self.fake.chmod(0o700)

    def event(self, document='MRD sample', task='task-a', revision=1, event_id='event-a'):
        return dict(event_id=event_id, source_message_id='source-a', project=bridge.PROJECT,
                    conversation_id='group-test', event_type='mrd_ready', task_id=task,
                    revision=revision, document=document, document_sha256=bridge.digest(document))

    def run_event(self, event=None):
        return self.pilot.execute(event or self.event(), codex=str(self.fake))

    def activate(self, record):
        return self.pilot.acknowledge(record['key'], 'group-result-1')

    def test_prepare_and_check_do_not_start_countdown_or_call_a_model(self):
        with patch.object(bridge.subprocess, 'Popen', side_effect=AssertionError('must not run')):
            self.assertEqual(self.pilot.check(self.event())['models_called'], 0)
        report = self.pilot.report()
        self.assertIsNone(report['activated_at'])
        self.assertEqual(report['runs'], 0)
        self.assertEqual(os.stat(self.pilot.root).st_mode & 0o777, 0o700)

    def test_reject_untrusted_scope_bad_hash_and_all_approval_events(self):
        for updates in [dict(project='other/repo'), dict(conversation_id='other-group'),
                        dict(event_type='spec_approved'), dict(event_type='develop'),
                        dict(document_sha256='wrong'), dict(task_id='../outside'), dict(revision=True)]:
            event = self.event()
            event.update(updates)
            with self.subTest(updates=updates), self.assertRaises(bridge.Blocked):
                self.pilot.check(event)
        self.assertEqual(self.pilot.report()['runs'], 0)

    def test_spec_usage_and_operator_receipt_keep_dev_disabled(self):
        result = self.run_event()
        self.assertEqual(result['status'], 'spec_ready')
        self.assertTrue(Path(result['spec_path']).is_file())
        self.assertFalse(result['notification_verified'])
        self.assertIsNone(self.pilot.report()['activated_at'])
        ack = self.activate(result)
        report = self.pilot.report()
        self.assertFalse(ack['receipt_independently_verified'])
        self.assertFalse(report['development_enabled'])
        self.assertAlmostEqual(report['expires_at'] - report['activated_at'], 72*3600)
        self.assertEqual(report['input_tokens'], 120)
        self.assertEqual(report['cached_input_tokens'], 100)
        self.assertEqual(report['output_tokens'], 20)  # reasoning already belongs to output
        self.activate(result)
        self.assertEqual(self.pilot.report()['expires_at'], report['expires_at'])
        with self.assertRaises(bridge.Blocked):
            self.pilot.acknowledge(result['key'], 'conflicting-group-result')

    def test_idempotency_survives_restart_and_new_delivery_id(self):
        first = self.run_event()
        restarted = bridge.Pilot(self.pilot.root)
        event = self.event(event_id='redelivery')
        with patch.object(bridge.subprocess, 'Popen', side_effect=AssertionError('must not execute')):
            with patch.object(bridge.Pilot, 'doctor', return_value={}):
                second = restarted.execute(event, codex=str(self.fake))
        self.assertEqual(second['status'], 'duplicate')
        self.assertEqual(second['key'], first['key'])
        self.assertEqual(restarted.report()['runs'], 1)

    def test_revision_change_and_event_reuse_cannot_reexecute(self):
        self.run_event()
        with self.assertRaises(bridge.Blocked):
            self.pilot.claim(self.event('changed MRD'))
        with self.assertRaises(bridge.Blocked):
            self.pilot.claim(self.event(task='different-task'))

    def test_probe_needs_group_receipt_before_a_second_task(self):
        first = self.run_event()
        next_event = self.event(task='task-b', event_id='event-b')
        with self.assertRaises(bridge.Blocked):
            self.pilot.claim(next_event)
        self.activate(first)
        second = self.run_event(next_event)
        self.assertEqual(second['status'], 'spec_ready')
        self.assertEqual(self.pilot.report()['runs'], 2)

    def test_pause_and_expiry_reject_new_model_work(self):
        first = self.run_event()
        self.activate(first)
        with self.pilot.state() as state:
            state['expires_at'] = time.time()-1
        with self.assertRaises(bridge.Blocked):
            self.pilot.claim(self.event(task='task-b', event_id='event-b'))
        self.pilot.pause()
        with self.assertRaises(bridge.Blocked):
            self.pilot.acknowledge(first['key'], 'another-receipt')

    def test_unknown_usage_is_not_zero_and_prevents_activation(self):
        record = self.run_event(self.event('UNKNOWN_USAGE_TEST'))
        self.assertEqual(record['status'], 'spec_ready')
        self.assertIsNone(record['usage'])
        self.assertEqual(self.pilot.report()['unknown_usage_runs'], 1)
        with self.assertRaises(bridge.Blocked):
            self.activate(record)

    def test_budget_and_run_limit_apply_between_runs(self):
        first = self.run_event()
        self.activate(first)
        with self.pilot.state() as state:
            state['max_input'] = 100
        with self.assertRaises(bridge.Blocked):
            self.pilot.claim(self.event(task='task-b', event_id='event-b'))
        with self.pilot.state() as state:
            state['max_input'] = 10000
            state['max_runs'] = 1
        with self.assertRaises(bridge.Blocked):
            self.pilot.claim(self.event(task='task-b', event_id='event-b'))

    def test_interrupted_claim_is_not_retried_after_restart(self):
        record, fresh = self.pilot.claim(self.event())
        self.assertTrue(fresh)
        again, fresh = bridge.Pilot(self.pilot.root).claim(self.event())
        self.assertFalse(fresh)
        self.assertEqual(again['status'], 'claimed')
        with self.assertRaises(bridge.Blocked):
            self.pilot.claim(self.event(task='task-b', event_id='event-b'))

    def test_failure_is_a_result_not_an_automatic_retry(self):
        record = self.run_event(self.event('FAIL_TEST'))
        self.assertEqual(record['status'], 'failed')
        self.assertEqual(record['exit_code'], 9)
        self.assertEqual(self.run_event(self.event('FAIL_TEST'))['original_status'], 'failed')

    def test_pause_can_interrupt_inflight_child_without_waiting_for_job_lock(self):
        errors = []
        results = []
        def run():
            try:
                results.append(self.run_event(self.event('SLOW_TEST')))
            except BaseException as exc:
                errors.append(exc)
        worker = threading.Thread(target=run)
        worker.start()
        end = time.monotonic()+5
        while not list((self.pilot.root / 'runs').glob('*/started')) and time.monotonic()<end:
            time.sleep(.02)
        self.pilot.pause()
        worker.join(5)
        self.assertFalse(worker.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(results[0]['status'], 'cancelled')

    def test_logs_with_multiple_usage_snapshots_or_invalid_cache_stay_unknown(self):
        path = self.root / 'usage.jsonl'
        event = {'type':'turn.completed','usage':{'input_tokens':3,'cached_input_tokens':4,'output_tokens':1}}
        path.write_text(json.dumps(event)+'\n')
        self.assertIsNone(self.pilot.usage(path))
        event['usage']['cached_input_tokens'] = 2
        path.write_text((json.dumps(event)+'\n')*2)
        self.assertIsNone(self.pilot.usage(path))

    def test_wrong_repository_is_rejected_before_state_is_created(self):
        subprocess.run(['git','-C',str(self.repo),'remote','set-url','origin','https://github.com/example/other.git'],check=True)
        other = bridge.Pilot(self.root/'other-state')
        with self.assertRaises(bridge.Blocked):
            other.init(self.repo,'group-test')
        self.assertFalse(other.root.exists())

    def test_cli_pipeline_with_fake_codex_produces_machine_readable_results(self):
        event_file = self.root/'event.json'
        event_file.write_text(json.dumps(self.event()))
        base = [sys.executable,str(MODULE),'--state',str(self.pilot.root)]
        done = subprocess.run(base+['run-spec','--event',str(event_file),'--codex',str(self.fake)],capture_output=True,text=True)
        self.assertEqual(done.returncode,0,done.stderr)
        payload = json.loads(done.stdout)
        self.assertEqual(payload['status'],'spec_ready')
        self.assertEqual(payload['usage']['input_tokens'],120)
        repeated = subprocess.run(base+['run-spec','--event',str(event_file),'--codex',str(self.fake)],capture_output=True,text=True)
        self.assertEqual(json.loads(repeated.stdout)['status'],'duplicate')
        report = json.loads(subprocess.check_output(base+['report'],text=True))
        self.assertEqual(report['runs'],1)
        self.assertEqual(report['duplicates'],1)
        self.assertIsNone(report['activated_at'])

    def test_api_key_environment_cannot_silently_change_pilot_billing(self):
        with patch.dict(os.environ, {'CODEX_API_KEY':'test-placeholder'}):
            with patch.object(bridge.subprocess, 'run', side_effect=AssertionError('must not invoke CLI')):
                with self.assertRaises(bridge.Blocked):
                    self.run_event()
        self.assertEqual(self.pilot.report()['runs'], 0)

    def test_existing_state_and_state_inside_checkout_are_not_overwritten(self):
        with self.assertRaises(bridge.Blocked):
            self.pilot.init(self.repo, 'group-test')
        with self.assertRaises(bridge.Blocked):
            bridge.Pilot(self.repo/'state').init(self.repo, 'group-test')


if __name__ == '__main__':
    unittest.main()
