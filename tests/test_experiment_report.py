import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from mini_se_workflow import comparison
from mini_se_workflow.experiment_report import export
from mini_se_workflow.store import RunStore


class ExperimentReportTests(unittest.TestCase):
    def test_export_preserves_both_runs_and_does_not_mislabel_fixture_results(self):
        item=next(x for x in json.loads(comparison.SUITE.read_text(encoding='utf-8')) if x['id']=='text-stats')
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            suite=root/'suite.json'
            suite.write_text(json.dumps([item],ensure_ascii=False),encoding='utf-8')
            output=root/'results.json'
            store=RunStore(root/'runs')
            with patch.object(comparison,'SUITE',suite):
                result=comparison.compare(comparison.ComparisonFixtureClient(),store,mode='comparison-fixture',repeats=1,output=output)
            markdown,archive=export(output,store)
            text=markdown.read_text(encoding='utf-8')
            self.assertIn('离线模拟',text)
            self.assertIn('单Agent | 1/1',text)
            self.assertIn('三Agent | 1/1',text)
            with zipfile.ZipFile(archive) as z:
                verification=json.loads(z.read('source-verification.json'))
                self.assertFalse(verification['suite'])  # Never archive a different suite as the original.
                self.assertNotIn('fixtures/comparison.json',z.namelist())
                for trial in result['trials']:
                    self.assertIn('runs/'+trial['run_id']+'/workflow.json',z.namelist())


if __name__=='__main__':unittest.main()
