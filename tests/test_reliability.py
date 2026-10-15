import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from mini_se_workflow import reliability
from mini_se_workflow.store import RunStore


class ReliabilityTests(unittest.TestCase):
    def test_fixed_trial_denominator_holdout_isolation_and_archive_hashes(self):
        class Client(reliability.ReliabilityFixtureClient):
            def __init__(self):
                super().__init__()
                self.prompts = []
            def complete_json(self, **kwargs):
                self.prompts.append(kwargs['system_prompt'] + kwargs['user_prompt'])
                return super().complete_json(**kwargs)
        client = Client()
        suite = json.loads(reliability.SUITE.read_text(encoding='utf-8'))
        for task in suite:
            for case in task['holdout']:
                case['description'] = 'HOLDOUT_IS_PRIVATE'
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            suite_path = root / 'suite.json'
            suite_path.write_text(json.dumps(suite, ensure_ascii=False), encoding='utf-8')
            output = root / 'result.json'
            with patch.object(reliability, 'SUITE', suite_path):
                result = reliability.study(client, RunStore(root / 'runs'), mode='fixture', output=output)
            self.assertTrue(result['complete'])
            self.assertEqual(result['metrics']['disabled']['success'], 0)
            self.assertEqual(result['metrics']['enabled']['success'], 3)
            self.assertEqual(result['metrics']['enabled']['corrections'], 3)
            self.assertEqual([r['arm'] for r in result['trials']],
                             ['disabled', 'enabled', 'enabled', 'disabled', 'disabled', 'enabled'])
            self.assertNotIn('HOLDOUT_IS_PRIVATE', ''.join(client.prompts))
            self.assertEqual(result['http_request_count'], 0)
            with zipfile.ZipFile(output.with_suffix('.zip')) as archive:
                for name, digest in result['implementation_sha256'].items():
                    self.assertEqual(hashlib.sha256(archive.read('implementation/' + name)).hexdigest(), digest)
                for row in result['trials']:
                    state = json.loads(archive.read('runs/' + row['run_id'] + '/workflow.json'))
                    self.assertEqual(state['independent_evaluation']['success'], row['success'])
            with self.assertRaisesRegex(ValueError, '已存在'):
                reliability.study(client, RunStore(root / 'other'), mode='fixture', output=output)

    def test_suite_cannot_silently_select_only_easy_tasks(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            suite_path = root / 'suite.json'
            suite_path.write_text('[]', encoding='utf-8')
            with patch.object(reliability, 'SUITE', suite_path), self.assertRaisesRegex(ValueError, '三个任务'):
                reliability.study(reliability.ReliabilityFixtureClient(), RunStore(root / 'runs'),
                                  mode='fixture', output=root / 'result.json')
