from __future__ import annotations

import copy
from typing import Callable
from uuid import uuid4

from .agents import CodingAgent, DesignAgent, RequirementsAgent
from .contracts import ContractError
from .demo import DEMO_TASK, benchmark_cases
from .models import WorkflowExecutionError, WorkflowState, timestamp
from .runner import AcceptanceRunner
from .store import RunStore


class MiniSEWorkflow:
    def __init__(self, client, store: RunStore, *, mode: str = "deepseek", max_repairs: int = 2, runner: AcceptanceRunner | None = None) -> None:
        if type(max_repairs) is not int or not 0 <= max_repairs <= 2:
            raise ValueError("最多返工次数必须在0到2之间。")
        self.requirements_agent = RequirementsAgent(client)
        self.design_agent = DesignAgent(client)
        self.coding_agent = CodingAgent(client)
        self.store = store
        self.mode = mode
        self.max_repairs = max_repairs
        self.runner = runner or AcceptanceRunner()

    def run(self, task: str, *, example_id: str | None = None, on_update: Callable[[dict], None] | None = None) -> WorkflowState:
        if not isinstance(task, str) or not task.strip() or len(task) > 6000:
            raise ValueError("需求必须是1到6000字符的文本。")
        task = task.strip()
        if example_id not in (None, "todo"):
            raise ValueError("示例类型无效。")
        if example_id == "todo" and task != DEMO_TASK:
            raise ValueError("固定示例验收仅适用于原始待办事项需求；自定义需求请取消示例标记。")
        if self.mode == "demo" and task != DEMO_TASK:
            raise ValueError("离线演示仅支持预置待办事项需求。")
        state = WorkflowState(uuid4().hex[:16], task, self.mode)

        def notify() -> None:
            snapshot = state.to_dict()
            self.store.save(snapshot)
            if on_update:
                on_update(snapshot)

        def event(step: str, agent: str, status: str, message: str) -> None:
            state.current_step = step
            state.events.append({"sequence": len(state.events) + 1, "time": timestamp(), "step": step, "agent": agent, "status": status, "message": message})
            notify()

        def send(sender: str, receiver: str, artifact: str, summary: str) -> None:
            state.messages.append({"sender": sender, "receiver": receiver, "artifact": artifact, "summary": summary})

        try:
            event("requirements", "需求 Agent", "running", "正在整理需求和可执行验收条件。")
            state.specification = self.requirements_agent.run(task)
            if state.specification.get("questions"):
                state.status = "needs_input"
                event("requirements", "需求 Agent", "needs_input", "需要补充需求后重新运行。")
                return state
            # The coder never receives authority to edit this snapshot or the benchmark suite.
            frozen_spec = copy.deepcopy(state.specification)
            cases = copy.deepcopy(frozen_spec["acceptance"])
            if example_id == "todo" or self.mode == "demo":
                fixed_cases = benchmark_cases()
                if self.mode != "demo":
                    # The live model may number its requirements differently from the demo fixture.
                    for fixed_case in fixed_cases:
                        fixed_case["requirement_ids"] = []
                cases.extend(fixed_cases)
            send("需求 Agent", "设计 Agent", "specification", state.specification["summary"])
            event("requirements", "需求 Agent", "completed", f"已固定 {len(frozen_spec['requirements'])} 条需求和 {len(cases)} 个验收用例。")
            event("design", "设计 Agent", "running", "正在定义文件职责、接口和数据结构。")
            state.design = self.design_agent.run(copy.deepcopy(frozen_spec))
            send("设计 Agent", "编码 Agent", "design + specification", state.design["summary"])
            event("design", "设计 Agent", "completed", f"已规划 {len(state.design['files'])} 个文件。")
            feedback = None
            for revision in range(self.max_repairs + 1):
                state.repair_count = revision
                coding_step = "coding" if revision == 0 else "repair"
                event(coding_step, "编码 Agent", "running", "正在生成完整项目。" if revision == 0 else f"正在依据失败反馈进行第 {revision} 次返工。")
                summary = ""
                try:
                    artifact = self.coding_agent.run(copy.deepcopy(frozen_spec), copy.deepcopy(state.design), files=copy.deepcopy(state.files) or None, feedback=copy.deepcopy(feedback))
                    state.files = artifact["files"]
                    summary = artifact["summary"]
                    send("编码 Agent", "验收执行器", "files", summary)
                    event(coding_step, "编码 Agent", "completed", summary)
                    event("validation", "验收执行器", "running", "正在实际启动项目并核对预期结果。")
                    report = self.runner.run(state.files, copy.deepcopy(cases), lambda result: event("validation", "验收执行器", "running", f"{result['id']} {result['description']}：{'通过' if result['passed'] else '未通过'}。"))
                except ContractError as exc:
                    report = {"passed": False, "error": str(exc), "source_checks": [], "cases": [], "total": len(cases), "passed_count": 0}
                    summary = "编码输出格式未通过校验。"
                self.store.revision(state.run_id, revision, state.files, report)
                state.iterations.append({"revision": revision, "summary": summary, "files": copy.deepcopy(state.files), "validation": report})
                if report["passed"]:
                    state.status = "approved"
                    send("验收执行器", "Workflow", "validation", "全部验收用例通过。")
                    event("done", "Workflow", "completed", f"验收通过：{report['passed_count']}/{report['total']}。项目可以下载。")
                    return state
                feedback = report
                send("验收执行器", "编码 Agent", "validation", f"验收通过 {report['passed_count']}/{report['total']}，携带实际错误、输入与输出返回修改。")
                event("validation", "验收执行器", "rejected", report.get("error") or f"验收通过 {report['passed_count']}/{report['total']}。")
            state.status = "failed_validation"
            event("done", "Workflow", "rejected", "已达到返工上限，保留项目与未通过的验收项。")
            return state
        except Exception as exc:
            state.status = "failed"
            state.error = str(exc)
            event(state.current_step, "Workflow", "failed", str(exc))
            raise WorkflowExecutionError(str(exc), state) from exc
