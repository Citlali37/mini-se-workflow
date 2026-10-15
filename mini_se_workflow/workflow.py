from __future__ import annotations

import copy
import os
import time
from typing import Callable
from uuid import uuid4

from .agents import CodingAgent, DesignAgent, RequirementsAgent, PlanningOutputError
from .llm import LLMResponseError
from .contracts import ContractError, specification as validate_specification
from .demo import DEMO_TASK, benchmark_cases
from .models import WorkflowCancelled, WorkflowExecutionError, WorkflowState, timestamp
from .runner import AcceptanceRunner
from .store import RunStore


class MiniSEWorkflow:
    def __init__(self, client, store: RunStore, *, mode: str = 'deepseek', max_repairs: int = 2,
                 runner: AcceptanceRunner | None = None, max_stage_corrections: int = 2) -> None:
        if type(max_repairs) is not int or not 0 <= max_repairs <= 5:
            raise ValueError('最多返工次数必须在0到5之间。')
        if type(max_stage_corrections) is not int or not 0 <= max_stage_corrections <= 2:
            raise ValueError('前置阶段纠正次数必须在0到2之间。')
        self.max_stage_corrections = max_stage_corrections
        self.requirements_agent = RequirementsAgent(client)
        self.design_agent = DesignAgent(client)
        self.coding_agent = CodingAgent(client)
        self.store, self.mode, self.max_repairs = store, mode, max_repairs
        self.runner = runner or AcceptanceRunner()

    def validate_task(self, task: str, example_id: str | None = None) -> str:
        if not isinstance(task, str) or not task.strip() or len(task) > 6000:
            raise ValueError('需求必须是1到6000字符的文本。')
        task = task.strip()
        if example_id not in (None, 'todo'):
            raise ValueError('示例类型无效。')
        if example_id == 'todo' and task != DEMO_TASK:
            raise ValueError('固定示例验收仅适用于原始待办事项需求。')
        if self.mode == 'demo' and task != DEMO_TASK:
            raise ValueError('离线演示仅支持预置待办事项需求。')
        return task

    def run(self, task: str, *, example_id: str | None = None, on_update: Callable[[dict], None] | None = None,
            require_confirmation: bool = False, should_cancel: Callable[[], bool] | None = None) -> WorkflowState:
        task = self.validate_task(task, example_id)
        state = WorkflowState(uuid4().hex[:16], task, self.mode, example_id=example_id,
                              max_repairs=self.max_repairs, review_required=require_confirmation,
                              max_stage_corrections=self.max_stage_corrections)
        return self._execute(state, on_update, should_cancel)

    def prepare_resume(self, run_id: str, *, action: str = 'retry', specification: dict | None = None, answer: str = '') -> WorkflowState:
        """Validate without mutating disk. Web calls this under its run lock."""
        raw = self.store.load(run_id)
        if 'next_step' not in raw:
            raise ValueError('旧版记录仅支持查看与下载，请新建任务。')
        state = WorkflowState.from_dict(raw)
        if state.mode != self.mode:
            raise ValueError('当前模型模式与历史任务不一致。')
        if action == 'confirm' and state.status == 'awaiting_confirmation':
            selected = validate_specification(copy.deepcopy(specification if specification is not None else state.specification))
            if selected.get('questions'):
                raise ValueError('仍有待确认问题，不能进入设计。')
            if self.mode == 'demo' and selected != state.specification:
                raise ValueError('离线模板不支持修改规格；请切换真实模型模式。')
            state.specification = selected
            state.confirmed_specification = copy.deepcopy(selected)
            state.confirmed_at = timestamp()
            state.requirement_history.append({'time': timestamp(), 'action': 'confirmed', 'specification': copy.deepcopy(selected)})
            state.next_step = 'design'
        elif action == 'clarify' and state.status == 'needs_input':
            if not isinstance(answer, str) or not answer.strip():
                raise ValueError('请填写待确认问题的答案。')
            task = state.task + '\n\n用户补充：\n' + answer.strip()
            self.validate_task(task)
            state.task, state.example_id = task, None
            state.requirement_history.append({'time': timestamp(), 'action': 'clarified', 'answer': answer.strip()})
            state.next_step = 'requirements'
        elif action == 'retry' and state.status in {'failed', 'interrupted', 'cancelled'}:
            if state.next_step not in {'requirements', 'design', 'coding', 'validation'}:
                raise ValueError('本次运行没有可恢复的检查点。')
        else:
            raise ValueError('当前状态不支持此操作；验收耗尽预算后请新建任务。')
        state.status, state.error = 'running', ''
        state.owner_pid = os.getpid()
        return state

    def resume(self, run_id: str, *, action: str = 'retry', specification: dict | None = None, answer: str = '',
               on_update: Callable[[dict], None] | None = None, should_cancel: Callable[[], bool] | None = None) -> WorkflowState:
        state = self.prepare_resume(run_id, action=action, specification=specification, answer=answer)
        return self._execute(state, on_update, should_cancel)

    def _execute(self, state: WorkflowState, on_update, should_cancel) -> WorkflowState:
        state.owner_pid = os.getpid()
        def notify():
            snapshot = state.to_dict()
            self.store.save(snapshot)
            if on_update:
                on_update(snapshot)

        def event(step, agent, status, message, **extra):
            state.current_step = step
            state.events.append({'sequence': len(state.events) + 1, 'time': timestamp(), 'step': step,
                                 'agent': agent, 'status': status, 'message': message, **extra})
            notify()

        def check_cancel():
            if should_cancel and should_cancel():
                raise WorkflowCancelled('已取消；检查点和已完成产物保留，可显式恢复。')

        def send(sender, receiver, artifact, summary):
            state.messages.append({'sender': sender, 'receiver': receiver, 'artifact': artifact, 'summary': summary})

        def call(step, agent, operation, message):
            check_cancel()
            event(step, agent, 'running', message)
            started = time.monotonic()
            result = operation()
            check_cancel()
            return result, round((time.monotonic() - started) * 1000)

        def planning_call(step, agent, operation, message):
            cycle = sum(item.get('action') == 'clarified' for item in state.requirement_history)
            record = state.planning.setdefault(f'{step}:{cycle}',
                {'stage': step, 'cycle': cycle, 'corrections_used': 0, 'attempts': [], 'feedback': None})
            started = time.monotonic()
            while True:
                check_cancel()
                feedback = copy.deepcopy(record['feedback'])
                if feedback:
                    if record['corrections_used'] >= state.max_stage_corrections:
                        raise ValueError(f'{agent}前置纠正预算已耗尽：' + feedback['error'])
                    record['corrections_used'] += 1
                attempt = {'time': timestamp(), 'status': 'running', 'correction': record['corrections_used']}
                record['attempts'].append(attempt)
                event(step, agent, 'running', message if not feedback else
                      f"正在纠正输出（{record['corrections_used']}/{state.max_stage_corrections}）：{feedback['error']}")
                try:
                    result = operation(feedback)
                except (PlanningOutputError, LLMResponseError) as exc:
                    attempt.update(status='invalid', feedback=copy.deepcopy(exc.feedback))
                    record['feedback'] = copy.deepcopy(exc.feedback)
                    send('输出校验', agent, 'correction_feedback', str(exc))
                    event(step, agent, 'rejected', str(exc))
                    continue
                except Exception as exc:
                    attempt.update(status='failed', error=str(exc))
                    notify()
                    raise
                attempt['status'] = 'completed'
                record['feedback'] = None
                notify()
                check_cancel()
                return result, round((time.monotonic() - started) * 1000)

        try:
            notify()
            if state.next_step == 'requirements':
                spec, elapsed = planning_call('requirements', '需求 Agent', lambda feedback: self.requirements_agent.run(state.task, feedback=feedback), '正在整理需求和可执行验收条件。')
                state.specification = spec
                state.requirement_history.append({'time': timestamp(), 'action': 'generated', 'specification': copy.deepcopy(spec)})
                if spec.get('questions'):
                    state.status = 'needs_input'
                    event('requirements', '需求 Agent', 'needs_input', '填写答案后继续当前任务。', duration_ms=elapsed)
                    return state
                if state.review_required:
                    state.status = 'awaiting_confirmation'
                    event('requirements', '需求 Agent', 'completed', '请检查并确认需求与验收条件，确认后进入设计。', duration_ms=elapsed)
                    return state
                state.confirmed_specification = copy.deepcopy(spec)
                state.confirmed_at = timestamp()
                state.next_step = 'design'
                event('requirements', '需求 Agent', 'completed', '需求与验收条件已固定（自动执行模式）。', duration_ms=elapsed)

            frozen_spec = copy.deepcopy(state.confirmed_specification)
            if not frozen_spec or frozen_spec.get('questions'):
                raise ValueError('缺少已确认的需求，不能继续执行。')
            cases = copy.deepcopy(frozen_spec['acceptance'])
            if state.example_id == 'todo' or self.mode == 'demo':
                fixed = benchmark_cases()
                if self.mode != 'demo':
                    for case in fixed:
                        case['requirement_ids'] = []
                cases.extend(fixed)

            if state.next_step == 'design':
                send('需求 Agent', '设计 Agent', 'specification', frozen_spec['summary'])
                plan, elapsed = planning_call('design', '设计 Agent', lambda feedback: self.design_agent.run(copy.deepcopy(frozen_spec), feedback=feedback), '正在定义文件职责、接口和数据结构。')
                state.design = plan
                state.next_step = 'coding'
                send('设计 Agent', '编码 Agent', 'design + specification', plan['summary'])
                event('design', '设计 Agent', 'completed', f"已规划 {len(plan['files'])} 个文件。", duration_ms=elapsed)

            while state.next_step in {'coding', 'validation'}:
                revision = len(state.iterations)
                state.repair_count = revision
                feedback = state.iterations[-1]['validation'] if state.iterations else None
                if state.next_step == 'coding':
                    step = 'coding' if revision == 0 else 'repair'
                    try:
                        artifact, elapsed = call(step, '编码 Agent', lambda: self.coding_agent.run(copy.deepcopy(frozen_spec), copy.deepcopy(state.design), files=copy.deepcopy(state.files) or None, feedback=copy.deepcopy(feedback)), '正在生成完整项目。' if revision == 0 else f'正在进行第 {revision} 次返工。')
                        state.files = artifact['files']
                        state.pending_artifact = {'summary': artifact['summary'], 'files': copy.deepcopy(state.files)}
                        state.next_step = 'validation'
                        send('编码 Agent', '验收执行器', 'files', artifact['summary'])
                        event(step, '编码 Agent', 'completed', artifact['summary'], duration_ms=elapsed)
                    except (ContractError, LLMResponseError) as exc:
                        state.pending_artifact = {'summary': '编码输出格式未通过校验。', 'files': {}, 'contract_error': str(exc)}
                        state.next_step = 'validation'
                        notify()
                check_cancel()
                pending = state.pending_artifact
                started = time.monotonic()
                event('validation', '验收执行器', 'running', '正在实际启动项目并核对预期结果。')
                if pending.get('contract_error'):
                    report = {'passed': False, 'error': pending['contract_error'], 'source_checks': [], 'cases': [], 'total': len(cases), 'passed_count': 0}
                else:
                    def progress(result):
                        check_cancel()
                        event('validation', '验收执行器', 'running', f"{result['id']} {result['description']}：{'通过' if result['passed'] else '未通过'}。")
                    report = self.runner.run(copy.deepcopy(pending['files']), copy.deepcopy(cases), progress, should_cancel=should_cancel)
                check_cancel()
                self.store.revision(state.run_id, revision, pending['files'], report)
                state.iterations.append({'revision': revision, 'summary': pending['summary'], 'files': copy.deepcopy(pending['files']), 'validation': report})
                state.pending_artifact = {}
                duration = round((time.monotonic() - started) * 1000)
                if report['passed']:
                    state.status, state.next_step = 'approved', 'done'
                    send('验收执行器', 'Workflow', 'validation', '全部验收用例通过。')
                    event('done', 'Workflow', 'completed', f"验收通过：{report['passed_count']}/{report['total']}。项目可以下载。", duration_ms=duration)
                    return state
                send('验收执行器', '编码 Agent', 'validation', f"验收通过 {report['passed_count']}/{report['total']}，携带实际错误、输入与输出返回修改。")
                if revision >= state.max_repairs:
                    state.status, state.next_step = 'failed_validation', 'done'
                    event('done', 'Workflow', 'rejected', '已达到返工上限，保留项目与未通过的验收项。', duration_ms=duration)
                    return state
                state.next_step = 'coding'
                event('validation', '验收执行器', 'rejected', report.get('error') or f"验收通过 {report['passed_count']}/{report['total']}。", duration_ms=duration)
            raise ValueError('无法识别下一执行阶段。')
        except WorkflowCancelled as exc:
            state.status = 'cancelled'
            event(state.current_step, 'Workflow', 'cancelled', str(exc))
            return state
        except Exception as exc:
            state.status, state.error = 'failed', str(exc)
            event(state.current_step, 'Workflow', 'failed', str(exc))
            raise WorkflowExecutionError(str(exc), state) from exc
