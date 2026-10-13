import io
import json
import tempfile
import unittest
import zipfile

from mini_se_workflow.demo import DEMO_TASK, DemoClient
from mini_se_workflow.reporting import delivery_report, revision_diffs
from mini_se_workflow.store import RunStore
from mini_se_workflow.workflow import MiniSEWorkflow


class ReportingTests(unittest.TestCase):
    def test_real_revision_diff_and_archive_report(self):
        with tempfile.TemporaryDirectory() as temp:
            store = RunStore(temp)
            state = MiniSEWorkflow(DemoClient(), store, mode='demo').run(DEMO_TASK)
            diffs = revision_diffs(state.to_dict())
            self.assertEqual(diffs[0]['failed_cases'], ['A4', 'B2'])
            change = next(c for c in diffs[1]['changes'] if c['file'] == 'service.py')
            self.assertIn('+        if not isinstance(title, str)', change['diff'])
            report = delivery_report(state.to_dict())
            self.assertIn('9/9', report)
            self.assertIn('R1', report)
            self.assertIn('A4', report)
            with zipfile.ZipFile(io.BytesIO(store.archive(state.run_id))) as archive:
                self.assertEqual(archive.read('_workflow/report.md').decode('utf-8'), report)

    def test_invalid_version_does_not_delete_diff_baseline(self):
        state = {'iterations': [{'revision':0,'files':{'main.py':'old\n'},'validation':{}},
            {'revision':1,'files':{},'validation':{'error':'非法输出'}},
            {'revision':2,'files':{'main.py':'new\n'},'validation':{}}]}
        result = revision_diffs(state)
        self.assertEqual(result[1]['changes'], [])
        self.assertEqual(result[2]['changes'][0]['kind'], 'modified')
        self.assertIn('-old', result[2]['changes'][0]['diff'])


if __name__ == '__main__':
    unittest.main()
