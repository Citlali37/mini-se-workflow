import copy
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from mini_se_workflow.contracts import ContractError, artifact, design, file_path, specification
from mini_se_workflow.demo import DEMO_TASK, DemoClient, todo_specification
from mini_se_workflow.models import WorkflowExecutionError
from mini_se_workflow.runner import AcceptanceRunner
from mini_se_workflow.store import RunStore
from mini_se_workflow.workflow import MiniSEWorkflow


class RecordingClient(DemoClient):
    def __init__(self, variant="normal"):
        self.calls = []
        self.variant = variant

    def complete_json(self, **kwargs):
        data = json.loads(kwargs["user_prompt"])
        self.calls.append((kwargs["agent_name"], copy.deepcopy(data)))
        if self.variant == "questions" and kwargs["agent_name"] == "requirements":
            return {"summary": "需明确保存方式", "questions": ["是否需要持久化？"]}
        if self.variant == "network_failure" and kwargs["agent_name"] == "design":
            raise RuntimeError("模拟接口不可用")
        result = super().complete_json(**kwargs)
        if kwargs["agent_name"] == "coding":
            if self.variant == "pass_first":
                corrected = dict(data, feedback={})
                result = super().complete_json(**dict(kwargs, user_prompt=json.dumps(corrected)))
            elif self.variant == "never_pass":
                result["files"]["main.py"] = 'print("not json")\n'
            elif self.variant == "bad_contract" and data.get("feedback") is None:
                del result["files"]["main.py"]
        return result


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = RunStore(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def run_workflow(self, client=None, repairs=2):
        client = client or RecordingClient()
        workflow = MiniSEWorkflow(client, self.store, mode="demo", max_repairs=repairs)
        return workflow.run(DEMO_TASK, example_id="todo"), client

    def test_real_execution_failure_feedback_repairs_project(self):
        state, client = self.run_workflow()
        self.assertEqual(state.status, "approved")
        self.assertEqual(state.repair_count, 1)
        self.assertEqual([r["validation"]["passed_count"] for r in state.iterations], [7, 9])
        calls = [data for name, data in client.calls if name == "coding"]
        self.assertEqual(calls[0]["specification"], calls[1]["specification"])
        self.assertEqual(calls[0]["design"], calls[1]["design"])
        feedback = calls[1]["feedback"]
        failed = next(c for c in feedback["cases"] if c["id"] == "A4")
        self.assertEqual(failed["steps"][0]["input"]["title"], "")
        self.assertFalse(failed["steps"][0]["passed"])
        self.assertEqual(self.store.load(state.run_id)["status"], "approved")
        self.assertTrue((self.store.directory(state.run_id) / "revision-1/project/main.py").is_file())
        with zipfile.ZipFile(io.BytesIO(self.store.archive(state.run_id))) as archive:
            self.assertIn("storage.py", archive.namelist())
            self.assertIn("_workflow/acceptance.json", archive.namelist())
            self.assertEqual(json.loads(archive.read("_workflow/workflow.json"))["status"], "approved")

    def test_first_pass_skips_repair(self):
        state, client = self.run_workflow(RecordingClient("pass_first"))
        self.assertEqual(state.status, "approved")
        self.assertEqual(state.repair_count, 0)
        self.assertEqual(len(client.calls), 3)

    def test_no_repairs_reports_failed_validation(self):
        state, _ = self.run_workflow(repairs=0)
        self.assertEqual(state.status, "failed_validation")
        self.assertEqual(len(state.iterations), 1)

    def test_repeated_failure_stops_after_two_repairs(self):
        state, client = self.run_workflow(RecordingClient("never_pass"))
        self.assertEqual(state.status, "failed_validation")
        self.assertEqual(state.repair_count, 2)
        self.assertEqual(sum(name == "coding" for name, _ in client.calls), 3)

    def test_invalid_coding_contract_can_be_repaired(self):
        state, client = self.run_workflow(RecordingClient("bad_contract"))
        self.assertEqual(state.status, "approved")
        self.assertIn("编码结果", state.iterations[0]["validation"]["error"])
        self.assertFalse(state.iterations[0]["files"])

    def test_questions_stop_before_design_and_coding(self):
        state, client = self.run_workflow(RecordingClient("questions"))
        self.assertEqual(state.status, "needs_input")
        self.assertEqual(len(client.calls), 1)
        self.assertFalse(state.files)

    def test_failure_preserves_completed_specification(self):
        workflow = MiniSEWorkflow(RecordingClient("network_failure"), self.store, mode="demo")
        with self.assertRaises(WorkflowExecutionError) as caught:
            workflow.run(DEMO_TASK)
        state = caught.exception.state
        self.assertEqual(state.status, "failed")
        self.assertEqual(state.current_step, "design")
        self.assertEqual(len(state.specification["requirements"]), 5)
        self.assertEqual(self.store.load(state.run_id)["error"], "模拟接口不可用")

    def test_demo_rejects_custom_task_and_mismatched_benchmark(self):
        workflow = MiniSEWorkflow(DemoClient(), self.store, mode="demo")
        with self.assertRaises(ValueError):
            workflow.run("其他项目")
        with self.assertRaises(ValueError):
            workflow.run("其他项目", example_id="todo")
        self.assertEqual(self.store.history(), [])


class ContractTests(unittest.TestCase):
    def test_paths_reject_escape_devices_and_reserved_metadata(self):
        for name in ("../main.py", "C:/main.py", "folder/main.py", "NUL.py", "workflow.json", "sitecustomize.py", "main.py "):
            with self.subTest(name=name):
                if name == "main.py ":
                    self.assertEqual(file_path(name), "main.py")
                else:
                    with self.assertRaises(ContractError):
                        file_path(name)

    def test_uncovered_requirement_is_rejected(self):
        payload = todo_specification()
        payload["requirements"].append({"id": "R6", "description": "新功能"})
        with self.assertRaises(ContractError):
            specification(payload)

    def test_empty_or_duplicate_acceptance_is_rejected(self):
        for change in ("empty", "duplicate"):
            payload = todo_specification()
            if change == "empty":
                payload["acceptance"][0]["steps"][0]["expected"] = {}
            else:
                payload["acceptance"].append(copy.deepcopy(payload["acceptance"][0]))
            with self.assertRaises(ContractError):
                specification(payload)

    def test_design_cannot_drop_requirements_or_readme(self):
        payload = {"summary": "设计", "files": [{"path": "main.py", "purpose": "入口", "requirement_ids": ["R1"]}], "interfaces": ["协议"], "data_model": "无存储"}
        with self.assertRaises(ContractError):
            design(payload, specification(todo_specification()))

    def test_coder_cannot_add_unplanned_file(self):
        with self.assertRaises(ContractError):
            artifact({"summary": "代码", "files": {"main.py": "print(1)", "extra.py": "print(2)"}}, {"files": [{"path": "main.py"}]})


if __name__ == "__main__":
    unittest.main()
