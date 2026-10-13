import copy
import json
import tempfile
import threading
import unittest

from mini_se_workflow.demo import DEMO_TASK, DemoClient, todo_specification
from mini_se_workflow.models import WorkflowExecutionError
from mini_se_workflow.runner import AcceptanceRunner
from mini_se_workflow.store import RunStore
from mini_se_workflow.workflow import MiniSEWorkflow


class Client(DemoClient):
    def __init__(self):
        self.calls = []
        self.fail_design = False
        self.ask = False

    def complete_json(self, **kwargs):
        self.calls.append((kwargs['agent_name'], json.loads(kwargs['user_prompt'])))
        if kwargs['agent_name'] == 'design' and self.fail_design:
            raise RuntimeError('模拟设计网络中断')
        if kwargs['agent_name'] == 'requirements' and self.ask and '用户补充' not in kwargs['user_prompt']:
            return {'questions': ['需要保存数据吗？']}
        if kwargs['agent_name'] == 'requirements' and '用户补充' in kwargs['user_prompt']:
            return todo_specification()
        return super().complete_json(**kwargs)


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = RunStore(self.temp.name)
        self.client = Client()
        self.workflow = MiniSEWorkflow(self.client, self.store)

    def tearDown(self):
        self.temp.cleanup()

    def test_review_edits_freeze_and_same_run(self):
        state = self.workflow.run(DEMO_TASK, require_confirmation=True)
        self.assertEqual(state.status, 'awaiting_confirmation')
        self.assertEqual([c[0] for c in self.client.calls], ['requirements'])
        edited = copy.deepcopy(state.specification)
        edited['requirements'][0]['description'] += '（人工核对）'
        result = self.workflow.resume(state.run_id, action='confirm', specification=edited)
        self.assertEqual(result.run_id, state.run_id)
        self.assertEqual(result.status, 'approved')
        design_call = next(data for name, data in self.client.calls if name == 'design')
        self.assertEqual(design_call['specification'], edited)
        self.assertEqual(result.confirmed_specification, edited)
        self.assertEqual(len(result.requirement_history), 2)
        with self.assertRaises(ValueError):
            self.workflow.resume(state.run_id, action='confirm')

    def test_invalid_confirmation_is_non_mutating(self):
        state = self.workflow.run(DEMO_TASK, require_confirmation=True)
        saved = self.store.load(state.run_id)
        with self.assertRaises(ValueError):
            self.workflow.resume(state.run_id, action='confirm', specification={'requirements': []})
        self.assertEqual(self.store.load(state.run_id), saved)

    def test_clarification_continues_original_run(self):
        self.client.ask = True
        state = self.workflow.run(DEMO_TASK, require_confirmation=True)
        self.assertEqual(state.status, 'needs_input')
        result = self.workflow.resume(state.run_id, action='clarify', answer='需要保存在本地文件。')
        self.assertEqual(result.run_id, state.run_id)
        self.assertEqual(result.status, 'awaiting_confirmation')
        self.assertIn('需要保存在本地文件', result.task)
        self.assertFalse(result.design)

    def test_design_retry_skips_requirements_and_keeps_budget(self):
        self.client.fail_design = True
        with self.assertRaises(WorkflowExecutionError) as caught:
            self.workflow.run(DEMO_TASK)
        self.client.fail_design = False
        result = self.workflow.resume(caught.exception.state.run_id)
        self.assertEqual(result.status, 'approved')
        self.assertEqual(sum(name == 'requirements' for name, _ in self.client.calls), 1)

    def test_validation_retry_reuses_pending_code(self):
        class FailingRunner(AcceptanceRunner):
            first = True
            def run(self, *args, **kwargs):
                if self.first:
                    self.first = False
                    raise OSError('模拟执行器故障')
                return super().run(*args, **kwargs)
        self.workflow.runner = FailingRunner()
        with self.assertRaises(WorkflowExecutionError) as caught:
            self.workflow.run(DEMO_TASK)
        state = caught.exception.state
        self.assertEqual(state.next_step, 'validation')
        result = self.workflow.resume(state.run_id)
        self.assertEqual(result.status, 'approved')
        self.assertEqual(sum(n == 'coding' for n, _ in self.client.calls), 2)

    def test_cancel_before_next_agent_then_resume(self):
        cancel = threading.Event()
        def update(s):
            if s['next_step'] == 'coding':
                cancel.set()
        state = self.workflow.run(DEMO_TASK, should_cancel=cancel.is_set, on_update=update)
        self.assertEqual(state.status, 'cancelled')
        self.assertEqual([n for n, _ in self.client.calls], ['requirements', 'design'])
        result = self.workflow.resume(state.run_id)
        self.assertEqual(result.status, 'approved')
        self.assertEqual(sum(n == 'design' for n, _ in self.client.calls), 1)

    def test_restart_marks_running_interrupted_and_restores(self):
        state = self.workflow.run(DEMO_TASK, require_confirmation=True)
        raw = state.to_dict()
        raw['status'] = 'running'
        raw['owner_pid'] = 99999999
        # Simulate interruption during requirements: re-run that incomplete node, then review.
        self.store.save(raw)
        self.store.recover_interrupted()
        self.assertEqual(self.store.load(state.run_id)['status'], 'interrupted')
        result = self.workflow.resume(state.run_id)
        self.assertEqual(result.status, 'awaiting_confirmation')

    def test_startup_does_not_interrupt_live_process(self):
        import os
        state = self.workflow.run(DEMO_TASK, require_confirmation=True)
        raw = state.to_dict()
        raw.update(status='running', owner_pid=os.getpid())
        self.store.save(raw)
        self.store.recover_interrupted()
        self.assertEqual(self.store.load(state.run_id)['status'], 'running')

    def test_exited_process_is_not_mistaken_for_live_owner(self):
        import subprocess
        import sys
        from mini_se_workflow.store import process_alive
        process = subprocess.Popen([sys.executable, '-c', 'pass'])
        process.wait(timeout=5)
        self.assertFalse(process_alive(process.pid))

    def test_exhausted_budget_and_legacy_records_cannot_bypass(self):
        workflow = MiniSEWorkflow(self.client, self.store, max_repairs=0)
        state = workflow.run(DEMO_TASK)
        self.assertEqual(state.status, 'failed_validation')
        with self.assertRaises(ValueError):
            workflow.resume(state.run_id)
        raw = state.to_dict()
        del raw['next_step']
        self.store.save(raw)
        with self.assertRaises(ValueError):
            workflow.resume(state.run_id)

    def test_configurable_bounded_repairs(self):
        self.assertEqual(MiniSEWorkflow(self.client, self.store, max_repairs=5).max_repairs, 5)
        for value in (-1, 6, True):
            with self.assertRaises(ValueError):
                MiniSEWorkflow(self.client, self.store, max_repairs=value)


if __name__ == '__main__':
    unittest.main()
