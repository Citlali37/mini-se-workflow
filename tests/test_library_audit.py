import copy
import json
import unittest
import tempfile

from mini_se_workflow.cli import ROOT
from mini_se_workflow.library_audit import CASES, load_files, publish_reviewed
from mini_se_workflow.runner import AcceptanceRunner, validate_fixtures
from mini_se_workflow.store import RunStore


class LibraryAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = json.loads(CASES.read_text(encoding='utf-8'))
        cls.original = load_files(ROOT/'examples/library-audit/original')
        cls.reviewed = load_files(ROOT/'examples/library-audit/reviewed')

    def test_original_defects_reproduce_without_altering_snapshot(self):
        cases = [c for c in self.cases if c['id'] in {'V1','S1','S5'}]
        result = AcceptanceRunner().run(self.original, cases)
        self.assertEqual(result['passed_count'], 0)
        corrupted = next(c for c in result['cases'] if c['id'] == 'S1')
        self.assertFalse(corrupted['steps'][0]['file_checks'][0]['passed'])
        snapshot = json.loads((ROOT/'examples/library-audit/original-workflow.json').read_text(encoding='utf-8'))
        self.assertEqual(self.original, snapshot['files'])

    def test_reviewed_passes_independent_business_and_storage_checks(self):
        result = AcceptanceRunner().run(self.reviewed, self.cases)
        self.assertTrue(result['passed'], [c['id'] for c in result['cases'] if not c['passed']])
        for case in result['cases']:
            for step in case['steps']:
                for check in step.get('file_checks', []):
                    self.assertTrue(check['passed'])

    def test_original_acceptance_is_still_satisfied(self):
        snapshot = json.loads((ROOT/'examples/library-audit/original-workflow.json').read_text(encoding='utf-8'))
        result = AcceptanceRunner().run(self.reviewed, snapshot['specification']['acceptance'])
        self.assertTrue(result['passed'])

    def test_fixtures_cannot_escape_or_shadow_source(self):
        base = {'id':'X','description':'夹具约束','steps':[{'input':{},'expected':{'ok':True}}]}
        payloads = [dict(initial_files={'../escape.json':'{}'}),
                    dict(initial_files={'main.py':'print(1)'}),
                    dict(initial_directories=['../escape.json.tmp']),
                    dict(initial_files={'data.json':'{}'}),
                    dict(steps=[{'input':{},'expected':{'ok':True},'preserve_files':['../secret.json']}])]
        for payload in payloads:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                validate_fixtures({'main.py':'print(1)','data.json':'source'}, [{**base, **payload}])

    def test_file_preservation_assertion_detects_false_error_response(self):
        files = {'main.py': 'from pathlib import Path\nimport json\nPath("data.json").write_text("changed")\nprint(json.dumps({"ok":False,"error":"rejected"}))\n'}
        cases = [{'id':'X','description':'错误响应不能掩盖写入','initial_files':{'data.json':'original'},
            'steps':[{'input':{},'expected':{'ok':False},'preserve_files':['data.json']}]}]
        result = AcceptanceRunner().run(files, cases)
        self.assertFalse(result['passed'])
        self.assertIn('数据文件', result['cases'][0]['steps'][0]['difference'])

    def test_publish_marks_human_review_and_keeps_original_record(self):
        result=json.loads((ROOT/'examples/library-audit/results.json').read_text(encoding='utf-8'))
        with tempfile.TemporaryDirectory() as temp:
            store=RunStore(temp)
            state=publish_reviewed(result,store)
            self.assertEqual(state.mode,'human_reviewed')
            self.assertNotEqual(state.run_id,result['source_run_id'])
            self.assertTrue(state.iterations[-1]['validation']['passed'])
            self.assertFalse(state.iterations[0]['validation']['passed'])
            self.assertEqual(state.independent_evaluation['report']['passed_count'],21)
            self.assertIn('不代表Agent自动返工',state.specification['summary'])
            altered=copy.deepcopy(result)
            altered['versions']['reviewed']['files_sha256']='stale'
            with self.assertRaises(ValueError):
                publish_reviewed(altered,store)


if __name__ == '__main__':
    unittest.main()
