"""Small preregistered comparison. Holdout checks never become generation/repair feedback."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import time
from pathlib import Path
from uuid import uuid4

from .agents import CodingAgent
from .cli import ROOT, load_env
from .contracts import ContractError, artifact
from .evaluation import FixtureClient
from .library_audit import load_files
from .llm import DeepSeekClient
from .models import WorkflowExecutionError, WorkflowState, timestamp
from .runner import AcceptanceRunner
from .store import RunStore
from .workflow import MiniSEWorkflow


SUITE = Path(__file__).with_name('fixtures')/'comparison.json'
SINGLE_PROMPT = CodingAgent.instructions().replace(
    '你是 Mini SE 中的编码 Agent。严格按照需求和设计生成完整项目。',
    '你是单Agent开发基线。直接根据原始需求自行分析、设计并生成完整项目，不调用其他Agent。')


class CountingClient:
    def __init__(self, client):
        self.client, self.calls = client, []

    def complete_json(self, **kwargs):
        entry = {'agent': kwargs['agent_name'], 'started_at': timestamp(), 'error': ''}
        self.calls.append(entry)
        started = time.monotonic()
        try:
            return self.client.complete_json(**kwargs)
        except Exception as exc:
            entry['error'] = str(exc)
            raise
        finally:
            entry['duration_ms'] = round((time.monotonic()-started)*1000)


class DevelopmentRunner(AcceptanceRunner):
    def __init__(self, cases):
        super().__init__()
        self.cases = copy.deepcopy(cases)

    def run(self, files, ignored_cases, on_case=None, **kwargs):
        return super().run(files, copy.deepcopy(self.cases), on_case, **kwargs)


def single_agent(client, item: dict, store: RunStore, mode: str) -> WorkflowState:
    state = WorkflowState(uuid4().hex[:16], item['task'], mode, max_repairs=2)
    state.specification = {'summary': '单Agent直接从原始需求生成项目；验收使用统一开发集。'}
    runner = DevelopmentRunner(item['development'])
    plan = None
    feedback = None
    def save(message, status='running'):
        state.events.append({'sequence':len(state.events)+1, 'time':timestamp(), 'step':state.current_step,
            'agent':'单Agent基线', 'status':status, 'message':message})
        store.save(state.to_dict())
    try:
        for revision in range(3):
            state.repair_count, state.current_step = revision, 'coding'
            save('初稿生成' if revision == 0 else f'第{revision}次返工')
            candidate_files, summary = {}, ''
            try:
                payload = client.complete_json(agent_name='single_agent', system_prompt=SINGLE_PROMPT,
                    user_prompt=json.dumps({'user_requirement':item['task'], 'previous_files':state.files or None,
                                            'feedback':feedback}, ensure_ascii=False))
                files = payload.get('files') if isinstance(payload, dict) else None
                if not isinstance(files, dict) or not 2 <= len(files) <= 10 or not {'main.py','README.md'} <= set(files):
                    raise ContractError('基线必须包含main.py、README.md，最多10个根目录文件。')
                candidate_plan = plan or {'files':[{'path':name} for name in files]}
                result = artifact(payload, candidate_plan)
                plan = candidate_plan
                state.files = candidate_files = result['files']
                summary = result['summary']
                state.current_step = 'validation'
                report = runner.run(candidate_files, [])
            except ContractError as exc:
                report = {'passed':False, 'error':str(exc), 'source_checks':[], 'cases':[],
                          'total':len(item['development']), 'passed_count':0}
                summary = '输出契约不合格'
            state.iterations.append({'revision':revision,'summary':summary,'files':copy.deepcopy(candidate_files),'validation':report})
            store.revision(state.run_id, revision, candidate_files, report)
            feedback = report
            if report['passed']:
                state.status, state.next_step = 'approved', 'done'
                save('统一开发集通过', 'completed')
                return state
            save('统一开发集未通过，保留反馈', 'rejected')
        state.status, state.next_step = 'failed_validation', 'done'
        save('返工预算耗尽', 'rejected')
    except Exception as exc:
        state.status, state.error = 'failed', str(exc)
        save(str(exc), 'failed')
    return state


class ComparisonFixtureClient:
    """Tests only. Scripted outputs must never be reported as model capability."""
    def __init__(self):
        self.task_case = None

    def complete_json(self, **kwargs):
        item = self.task_case
        if item['id'] == 'library':
            files = load_files(ROOT/'examples/library-audit/reviewed')
            if kwargs['agent_name'] in {'coding','single_agent'}:
                return {'summary':'人工固定模板用于离线机制检查','files':files}
            if kwargs['agent_name'] == 'requirements':
                return {'project_name':'library-fixture','summary':'固定模板','assumptions':[],'questions':[],
                    'requirements':[{'id':'R1','description':item['task']}],
                    'acceptance':[{**copy.deepcopy(item['development'][0]),'requirement_ids':['R1']}]}
            return {'summary':'固定设计','files':[{'path':name,'purpose':'模板文件','requirement_ids':['R1']} for name in files],
                    'interfaces':['JSON协议'],'data_model':'library_data.json'}
        adapter = FixtureClient({'id':item['id'], 'task':item['task'],'expected':'project','checks':item['development']})
        forwarded = dict(kwargs)
        if forwarded['agent_name'] == 'single_agent':
            forwarded['agent_name'] = 'coding'
        return adapter.complete_json(**forwarded)


def schedule(items: list[dict], repeats: int) -> list[tuple]:
    ordered = []
    for repeat in range(repeats):
        for index, item in enumerate(items):
            arms = ('single','multi') if (repeat+index)%2 == 0 else ('multi','single')
            ordered.extend((repeat, item, arm) for arm in arms)
    return ordered


def summary(results: list[dict]) -> dict:
    metrics = {}
    for arm in ('single','multi'):
        rows = [r for r in results if r['arm'] == arm]
        metrics[arm] = {'trials':len(rows), 'success':sum(r['success'] for r in rows),
            'success_rate':sum(r['success'] for r in rows)/len(rows) if rows else 0,
            'first_pass_success':sum(r['success'] and r['repair_count']==0 for r in rows),
            'repair_count':sum(r['repair_count'] for r in rows),
            'logical_calls':sum(r['logical_calls'] for r in rows),
            'http_requests':sum(r['http_requests'] for r in rows),
            'duration_ms':sum(r['duration_ms'] for r in rows),
            'prompt_tokens':sum(r['prompt_tokens'] for r in rows),
            'completion_tokens':sum(r['completion_tokens'] for r in rows)}
        metrics[arm]['recorded_cost_peak_uncached_cny'] = round((metrics[arm]['prompt_tokens']*2 + metrics[arm]['completion_tokens']*8)/1000000, 6)
    return metrics


def compare(client, store: RunStore, *, mode: str, repeats: int = 2, output: Path | None = None) -> dict:
    if repeats not in (1,2):
        raise ValueError('预注册小实验只支持1或2次重复。')
    suite_bytes = SUITE.read_bytes()
    suite = json.loads(suite_bytes)
    tracked = CountingClient(client)
    report = {'created_at':timestamp(), 'mode':mode, 'suite_sha256':hashlib.sha256(suite_bytes).hexdigest(),
        'description':'真实单Agent/三Agent小样本对照，保留全部结果' if mode=='deepseek' else '离线模拟，仅验证实验机制',
        'repeats':repeats, 'max_repairs':2, 'holdout_policy':'独立测试不用于生成或返工反馈，失败后不追加挑选运行',
        'order': [{'repeat':repeat+1,'task':item['id'],'arm':arm} for repeat,item,arm in schedule(suite,repeats)],
        'settings':{k:getattr(client,k,None) for k in ('model','thinking','reasoning_effort','timeout_seconds','max_tokens','request_limit')},
        'implementation_sha256':{name:hashlib.sha256((Path(__file__).parent/name).read_bytes()).hexdigest()
                                 for name in ('agents.py','workflow.py','runner.py','comparison.py')},
        'trials':[], 'metrics':{}}
    for repeat, item, arm in schedule(suite, repeats):
        if mode != 'deepseek':
            client.task_case = item
        before_calls = len(tracked.calls)
        before_requests = getattr(client,'request_count',0)
        before_usage = len(getattr(client,'usage_records',[]))
        started = time.monotonic()
        if arm == 'single':
            state = single_agent(tracked, item, store, mode)
        else:
            workflow = MiniSEWorkflow(tracked, store, mode=mode, max_repairs=2, runner=DevelopmentRunner(item['development']))
            try:
                state = workflow.run(item['task'])
            except WorkflowExecutionError as exc:
                state = exc.state
        heldout = AcceptanceRunner().run(state.files, copy.deepcopy(item['holdout'])) if state.files else None
        success = state.status == 'approved' and bool(heldout and heldout['passed'])
        usage = copy.deepcopy(getattr(client,'usage_records',[])[before_usage:])
        trial = {'repeat':repeat+1, 'task':item['id'], 'arm':arm, 'run_id':state.run_id, 'status':state.status,
            'success':success, 'repair_count':state.repair_count, 'error':state.error,
            'development_case_ids':[c['id'] for c in item['development']], 'holdout':heldout,
            'logical_calls':len(tracked.calls)-before_calls, 'http_requests':getattr(client,'request_count',0)-before_requests,
            'duration_ms':round((time.monotonic()-started)*1000), 'calls':copy.deepcopy(tracked.calls[before_calls:]),
            'usage_records':usage, 'prompt_tokens':sum(u['usage'].get('prompt_tokens',0) for u in usage),
            'completion_tokens':sum(u['usage'].get('completion_tokens',0) for u in usage),
            'files_sha256':hashlib.sha256(json.dumps(state.files,sort_keys=True,ensure_ascii=False).encode('utf-8')).hexdigest()}
        state.independent_evaluation = {'case_id':item['id'], 'mode':mode, 'expected':'project','success':success,
                                       'suite_sha256':report['suite_sha256'],'report':heldout}
        store.save(state.to_dict())
        report['trials'].append(trial)
        report['metrics'] = summary(report['trials'])
        if output:
            output.parent.mkdir(parents=True,exist_ok=True)
            output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(f"repeat={repeat+1} {item['id']} {arm}: {'PASS' if success else 'FAIL'} [{state.status}] requests={trial['http_requests']}",flush=True)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description='预注册单/三Agent小实验；默认仅离线机制验证。')
    parser.add_argument('--real',action='store_true')
    parser.add_argument('--repeats',type=int,choices=[1,2],default=2)
    parser.add_argument('--request-limit',type=int,default=60)
    parser.add_argument('--max-tokens',type=int,default=16384)
    parser.add_argument('--output',default=str(ROOT/'outputs/comparison-fixture.json'))
    parser.add_argument('--run-root',default=str(ROOT/'outputs/comparison/runs'))
    args = parser.parse_args(argv)
    if not 1 <= args.request_limit <= 100 or not 1024 <= args.max_tokens <= 16384:
        parser.error('请求预算1–100，输出token预算1024–16384。')
    if args.real:
        load_env(ROOT/'.env')
        client = DeepSeekClient(os.getenv('LLM_BASE_URL','https://api.deepseek.com'),
            os.getenv('DEEPSEEK_API_KEY') or os.getenv('LLM_API_KEY',''),os.getenv('LLM_MODEL','deepseek-flash'),
            timeout_seconds=float(os.getenv('LLM_TIMEOUT_SECONDS','60')),max_retries=int(os.getenv('LLM_MAX_RETRIES','3')),
            thinking=os.getenv('LLM_THINKING') or None,reasoning_effort=os.getenv('LLM_REASONING_EFFORT') or None,
            max_tokens=args.max_tokens,request_limit=args.request_limit)
    else:
        client = ComparisonFixtureClient()
    report = compare(client,RunStore(args.run_root),mode='deepseek' if args.real else 'comparison-fixture',repeats=args.repeats,output=Path(args.output))
    print(json.dumps(report['metrics'],ensure_ascii=False),flush=True)
    return 0 if all(t['success'] for t in report['trials']) else 2


if __name__ == '__main__':
    raise SystemExit(main())
