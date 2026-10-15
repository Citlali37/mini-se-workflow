import copy
import json
import tempfile
import unittest
from pathlib import Path

from mini_se_workflow.verification import ROOT, check_report, run_check


class VerificationTests(unittest.TestCase):
    def test_saved_evidence_and_expected_original_failures_are_accepted(self):
        for name, path in (("evaluation", "evaluation-fixture.json"),
                           ("comparison", "comparison-fixture.json"),
                           ("library-audit", "library-audit/results.json")):
            report = json.loads((ROOT / "examples" / path).read_text(encoding="utf-8"))
            check_report(name, report)

    def test_real_mode_and_falsified_pass_counts_are_rejected(self):
        report = json.loads((ROOT / "examples/evaluation-fixture.json").read_text(encoding="utf-8"))
        report["mode"] = "deepseek"
        with self.assertRaises(ValueError):
            check_report("evaluation", report)
        audit = json.loads((ROOT / "examples/library-audit/results.json").read_text(encoding="utf-8"))
        changed = copy.deepcopy(audit)
        changed["versions"]["reviewed"]["independent"]["cases"][0]["passed"] = False
        with self.assertRaises(ValueError):
            check_report("library-audit", changed)

    def test_failed_process_and_missing_artifact_cannot_pass(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            result = run_check("unittest", ["-c", "import sys; print('failure detail'); sys.exit(3)"], directory)
            self.assertFalse(result["passed"])
            self.assertEqual(result["returncode"], 3)
            self.assertIn("failure detail", (directory / "unittest.log").read_text(encoding="utf-8"))
            result = run_check("evaluation", ["-c", "pass"], directory, directory / "missing.json")
            self.assertFalse(result["passed"])
            self.assertEqual(result["returncode"], 0)


if __name__ == "__main__":
    unittest.main()
