import os
import unittest
from unittest.mock import patch

from mini_se_workflow.runner import AcceptanceRunner, compare_json, source_checks


def acceptance(*steps):
    return [{"id": "T1", "description": "实际执行", "steps": list(steps)}]


def step(request, expected):
    return {"input": request, "expected": expected}


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.runner = AcceptanceRunner(step_timeout=1)

    def test_json_comparison_detects_boolean_and_array_errors(self):
        self.assertIsNotNone(compare_json({"ok": 1}, {"ok": True}))
        self.assertIsNotNone(compare_json({"items": [1, 2]}, {"items": [1]}))
        self.assertIsNone(compare_json({"ok": True, "extra": 4}, {"ok": True}))
        self.assertIsNotNone(compare_json({}, {"ok": True}))

    def test_process_restart_preserves_only_local_files(self):
        source = 'import json\nfrom pathlib import Path\np=Path("count.txt")\nn=int(p.read_text())+1 if p.exists() else 1\np.write_text(str(n))\nprint(json.dumps({"n":n}))\n'
        cases = acceptance(step({}, {"n": 1}), step({}, {"n": 2}))
        cases.append({"id": "T2", "description": "独立目录", "steps": [step({}, {"n": 1})]})
        result = self.runner.run({"main.py": source}, cases)
        self.assertTrue(result["passed"])

    def test_timeout_returns_feedback(self):
        result = AcceptanceRunner(step_timeout=0.2).run({"main.py": "while True:\n    pass\n"}, acceptance(step({}, {"ok": True})))
        self.assertFalse(result["passed"])
        self.assertIn("超时", result["cases"][0]["steps"][0]["error"])

    def test_output_limit_and_non_json_are_failures(self):
        for source in ('print("x" * 100000)\n', 'print("hello")\n', 'print("{} {}")\n', 'print("{\\"value\\": NaN}")\n'):
            with self.subTest(source=source):
                result = self.runner.run({"main.py": source}, acceptance(step({}, {"ok": True})))
                self.assertFalse(result["passed"])

    def test_api_credentials_are_not_in_child_environment(self):
        # The scope check rejects os imports; this separate observation uses sys to inspect injected environment indirectly.
        from mini_se_workflow.runner import execute_request
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "main.py").write_text('import os,json\nprint(json.dumps({"leaked":"DEEPSEEK_API_KEY" in os.environ,"value":os.environ.get("PYTHONPATH")}))\n', encoding="utf-8")
            with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-secret", "PYTHONPATH": "test-path"}):
                output = execute_request(root, {}, 2)
            self.assertEqual(output["actual"], {"leaked": False, "value": None})

    def test_source_checks_prevent_unsupported_imports_and_invalid_syntax(self):
        for source in ("import subprocess\n", "import socket\n", "eval('1')\n", "return 1\n", "def broken(:\n"):
            with self.subTest(source=source):
                result = self.runner.run({"main.py": source}, acceptance(step({}, {"ok": True})))
                self.assertFalse(result["passed"])
                self.assertFalse(result["cases"])
                self.assertTrue(result["source_checks"][0]["errors"])


if __name__ == "__main__":
    unittest.main()
