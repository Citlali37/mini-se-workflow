import copy
import io
import json
import tempfile
import threading
import unittest
from unittest.mock import patch

from mini_se_workflow.demo import DEMO_TASK, DemoClient
from mini_se_workflow.llm import DeepSeekClient, LLMError, LLMResponseError
from mini_se_workflow.models import WorkflowExecutionError
from mini_se_workflow.reporting import delivery_report
from mini_se_workflow.store import RunStore
from mini_se_workflow.workflow import MiniSEWorkflow


class InjectedClient(DemoClient):
    def __init__(self, stage='requirements', failures=1, kind='coverage'):
        self.stage, self.remaining, self.kind = stage, failures, kind
        self.calls = []

    def complete_json(self, **kwargs):
        name = kwargs['agent_name']
        self.calls.append((name, json.loads(kwargs['user_prompt'])))
        if name == self.stage and self.remaining:
            self.remaining -= 1
            if self.kind == 'auth':
                raise LLMError('HTTP 401: test authentication failure')
            if self.kind == 'json':
                raise LLMResponseError('JSON无效', content='{"partial":')
            payload = copy.deepcopy(super().complete_json(**kwargs))
            if name == 'requirements':
                payload['acceptance'] = payload['acceptance'][:1]
            else:
                payload['files'] = [f for f in payload['files'] if f['path'] != 'README.md']
            return payload
        return super().complete_json(**kwargs)


class PlanningTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = RunStore(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_missing_coverage_is_corrected_with_specific_feedback(self):
        client = InjectedClient()
        state = MiniSEWorkflow(client, self.store).run(DEMO_TASK, require_confirmation=True)
        self.assertEqual(state.status, 'awaiting_confirmation')
        self.assertEqual([name for name, _ in client.calls], ['requirements', 'requirements'])
        feedback = client.calls[1][1]['correction_feedback']
        self.assertIn('R3', feedback['error'])
        self.assertEqual(state.planning['requirements:0']['corrections_used'], 1)
        self.assertEqual(state.repair_count, 0)
        self.assertIn('调用2次；纠正1/2次', delivery_report(state.to_dict()))

    def test_design_correction_preserves_frozen_specification(self):
        client = InjectedClient(stage='design')
        workflow = MiniSEWorkflow(client, self.store)
        state = workflow.run(DEMO_TASK, require_confirmation=True)
        frozen = copy.deepcopy(state.specification)
        state = workflow.resume(state.run_id, action='confirm')
        self.assertEqual(state.status, 'approved')
        designs = [data for name, data in client.calls if name == 'design']
        self.assertEqual(len(designs), 2)
        self.assertEqual(designs[0]['specification'], frozen)
        self.assertEqual(designs[1]['specification'], frozen)
        self.assertEqual(state.confirmed_specification, frozen)
        self.assertIn('README.md', designs[1]['correction_feedback']['error'])

    def test_invalid_json_is_correctable_but_authentication_is_not(self):
        for kind, calls, status in [('json', 2, 'awaiting_confirmation'), ('auth', 1, 'failed')]:
            client = InjectedClient(kind=kind)
            workflow = MiniSEWorkflow(client, self.store)
            if kind == 'auth':
                with self.assertRaises(WorkflowExecutionError) as caught:
                    workflow.run(DEMO_TASK, require_confirmation=True)
                state = caught.exception.state
            else:
                state = workflow.run(DEMO_TASK, require_confirmation=True)
            self.assertEqual(len(client.calls), calls)
            self.assertEqual(state.status, status)

    def test_budget_exhaustion_cannot_be_reset_by_resume_or_new_configuration(self):
        client = InjectedClient(failures=99)
        workflow = MiniSEWorkflow(client, self.store)
        with self.assertRaises(WorkflowExecutionError) as caught:
            workflow.run(DEMO_TASK)
        state = caught.exception.state
        self.assertEqual(len(client.calls), 3)
        self.assertEqual(state.planning['requirements:0']['corrections_used'], 2)
        with self.assertRaises(WorkflowExecutionError):
            MiniSEWorkflow(client, self.store, max_stage_corrections=0).resume(state.run_id)
        self.assertEqual(len(client.calls), 3)
        self.assertFalse(state.design)

    def test_cancel_before_correction_retains_feedback_for_same_run(self):
        client = InjectedClient()
        cancel = threading.Event()
        def observe(snapshot):
            if snapshot['events'] and snapshot['events'][-1]['status'] == 'rejected':
                cancel.set()
        workflow = MiniSEWorkflow(client, self.store)
        state = workflow.run(DEMO_TASK, require_confirmation=True, should_cancel=cancel.is_set, on_update=observe)
        self.assertEqual(state.status, 'cancelled')
        self.assertEqual(len(client.calls), 1)
        result = workflow.resume(state.run_id)
        self.assertEqual(result.status, 'awaiting_confirmation')
        self.assertEqual(result.run_id, state.run_id)
        self.assertIn('correction_feedback', client.calls[1][1])

    def test_disabled_correction_stops_at_first_error(self):
        client = InjectedClient()
        with self.assertRaises(WorkflowExecutionError):
            MiniSEWorkflow(client, self.store, max_stage_corrections=0).run(DEMO_TASK)
        self.assertEqual(len(client.calls), 1)

    def test_coding_json_error_uses_code_repair_budget(self):
        client = InjectedClient(stage='coding', kind='json')
        state = MiniSEWorkflow(client, self.store).run(DEMO_TASK)
        self.assertEqual(state.status, 'approved')
        self.assertEqual(state.repair_count, 1)
        self.assertFalse(state.iterations[0]['files'])
        self.assertEqual(state.iterations[0]['validation']['error'], 'JSON无效')
        self.assertEqual(sum(r['corrections_used'] for r in state.planning.values()), 0)

    def test_clarification_starts_new_bounded_round(self):
        class Client(InjectedClient):
            def complete_json(self, **kwargs):
                data = json.loads(kwargs['user_prompt'])
                if kwargs['agent_name'] == 'requirements' and '用户补充' not in data['user_requirement']:
                    self.calls.append(('requirements', data))
                    return {'questions': ['是否需要持久化？']}
                if kwargs['agent_name'] == 'requirements':
                    kwargs = {**kwargs, 'user_prompt': json.dumps({**data, 'user_requirement': DEMO_TASK})}
                return super().complete_json(**kwargs)
        client = Client()
        workflow = MiniSEWorkflow(client, self.store)
        state = workflow.run(DEMO_TASK, require_confirmation=True)
        self.assertEqual(state.status, 'needs_input')
        state = workflow.resume(state.run_id, action='clarify', answer='需要持久化。')
        self.assertEqual(state.status, 'awaiting_confirmation')
        self.assertEqual(state.planning['requirements:0']['corrections_used'], 0)
        self.assertEqual(state.planning['requirements:1']['corrections_used'], 1)

    def test_length_finish_reason_rejects_even_parseable_content_and_preserves_usage(self):
        client = DeepSeekClient('https://api.deepseek.com', 'test-key', 'test-model')
        response = io.BytesIO(json.dumps({'choices': [{'finish_reason': 'length',
            'message': {'content': '{"ok": true}', 'reasoning_content': 'PRIVATE_REASONING'}}],
            'usage': {'completion_tokens': 16384}}).encode())
        with patch('urllib.request.urlopen', return_value=response) as request:
            with self.assertRaises(LLMResponseError) as caught:
                client.complete_json(agent_name='requirements', system_prompt='s', user_prompt='u')
        self.assertEqual(request.call_count, 1)
        self.assertEqual(caught.exception.feedback['kind'], 'output_truncated')
        self.assertNotIn('PRIVATE_REASONING', str(caught.exception.feedback))
        self.assertEqual(client.usage_records[0]['usage']['completion_tokens'], 16384)

    def test_explicit_default_output_budget_and_invalid_limits(self):
        for value in (True, 1023, 65537):
            with self.assertRaises(ValueError):
                DeepSeekClient('https://api.deepseek.com', 'test-key', 'test-model', max_tokens=value)
        client = DeepSeekClient('https://api.deepseek.com', 'test-key', 'test-model')
        response = io.BytesIO(json.dumps({'choices': [{'message': {'content': '{"ok":true}'}}]}).encode())
        with patch('urllib.request.urlopen', return_value=response) as request:
            client.complete_json(agent_name='coding', system_prompt='s', user_prompt='u')
        self.assertEqual(json.loads(request.call_args.args[0].data)['max_tokens'], 32768)
