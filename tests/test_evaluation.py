import copy
import json
import tempfile
import unittest
from pathlib import Path

from mini_se_workflow.evaluation import FixtureClient, SUITE, evaluate, summarize
from mini_se_workflow.store import RunStore


class EvaluationTests(unittest.TestCase):
    def test_independent_failure_is_retained_despite_workflow_pass(self):
        item = next(c for c in json.loads(SUITE.read_text(encoding='utf-8')) if c['id'] == 'text-stats')
        class MissingBoundaryClient(FixtureClient):
            def complete_json(self, **kwargs):
                result = super().complete_json(**kwargs)
                if kwargs['agent_name'] == 'coding':
                    result['files']['main.py'] = result['files']['main.py'].replace(
                        "if not isinstance(t,str): return {'ok':False,'error':'invalid_text'}",
                        "if not isinstance(t,str): return {'ok':True,'characters':0,'words':0,'lines':0}")
                return result
        client = MissingBoundaryClient(item)
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)/'report.json'
            report = evaluate(client, RunStore(Path(temp)/'runs'), mode='test-double', selected=['text-stats'], output=output)
            result = report['results'][0]
            self.assertEqual(result['status'], 'approved')
            self.assertFalse(result['success'])
            self.assertFalse(result['independent']['passed'])
            failed = next(c for c in result['independent']['cases'] if not c['passed'])
            self.assertEqual(failed['id'], 'S4')
            self.assertEqual(json.loads(output.read_text(encoding='utf-8'))['metrics']['success'], 0)
            self.assertEqual(client.calls, 3)  # Holdout failures never get returned to the coder.
            from mini_se_workflow.reporting import delivery_report
            saved = RunStore(Path(temp)/'runs').load(result['run_id'])
            self.assertEqual(saved['status'], 'approved')
            self.assertFalse(saved['independent_evaluation']['success'])
            self.assertIn('独立用例：3/4', delivery_report(saved))

    def test_first_pass_denominator_excludes_clarification(self):
        records = [dict(expected='project',success=True,repair_count=0,category='normal'),
                   dict(expected='project',success=True,repair_count=1,category='normal'),
                   dict(expected='questions',success=True,repair_count=0,category='ambiguity')]
        self.assertEqual(summarize(records)['first_pass_rate'], .5)
        self.assertEqual(summarize(records)['success_rate'], 1)

    def test_unknown_suite_selection_rejected_before_calls(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ValueError):
                evaluate(None, RunStore(temp), mode='fixture', selected=['unknown'])


if __name__ == '__main__':
    unittest.main()
