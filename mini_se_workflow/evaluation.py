"""Fixed holdout checks are never supplied to the coding agent or its repair feedback."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path

from .cli import ROOT, load_env
from .demo import DEMO_TASK, DemoClient, todo_specification
from .llm import DeepSeekClient
from .models import WorkflowExecutionError, timestamp
from .runner import AcceptanceRunner
from .store import RunStore
from .workflow import MiniSEWorkflow


SUITE = Path(__file__).with_name('fixtures') / 'evaluation.json'


class FixtureClient(DemoClient):
    """Scripted mechanism tests, deliberately labelled separately from model evaluation."""
    def __init__(self, task_case):
        self.task_case = task_case
        self.calls = 0

    def complete_json(self, **kwargs):
        self.calls += 1
        item = self.task_case
        if item['id'] == 'todo':
            return super().complete_json(**kwargs)
        if item['expected'] == 'questions':
            return {'summary': '固定模拟响应', 'questions': ['请明确转换规则或调整项目范围。']}
        if kwargs['agent_name'] == 'requirements':
            return {'project_name': item['id'], 'summary': '离线机制验证规格', 'assumptions': [], 'questions': [],
                'requirements': [{'id': 'R1', 'description': item['task']}],
                'acceptance': [{**copy.deepcopy(item['checks'][0]), 'requirement_ids': ['R1']}]}
        if kwargs['agent_name'] == 'design':
            return {'summary': '离线固定设计', 'files': [
                {'path': 'main.py', 'purpose': '入口', 'requirement_ids': ['R1']},
                {'path': 'README.md', 'purpose': '说明', 'requirement_ids': ['R1']}],
                'interfaces': ['stdin/stdout JSON'], 'data_model': '固定机制测试'}
        bodies = {
            'text-stats': '''import re
def handle(r):
    t=r.get('text')
    if not isinstance(t,str): return {'ok':False,'error':'invalid_text'}
    return {'ok':True,'characters':len(t),'words':len(re.findall(r'[A-Za-z0-9]+',t)),'lines':len(t.splitlines())}
''',
            'grades': '''import math
def handle(r):
    s=r.get('scores')
    if not isinstance(s,list) or any(type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=100 for v in s): return {'ok':False,'error':'invalid_scores'}
    if not s: return {'ok':False,'error':'empty_scores'}
    return {'ok':True,'count':len(s),'average':round(sum(s)/len(s),2),'minimum':min(s),'maximum':max(s),'passed':sum(v>=60 for v in s)}
''',
            'ledger': '''from pathlib import Path
def handle(r):
    p=Path('entries.json'); entries=json.loads(p.read_text(encoding='utf-8')) if p.exists() else []
    action=r.get('action')
    if action=='list': return {'ok':True,'entries':entries}
    if action=='total': return {'ok':True,'total':sum(e['amount'] for e in entries)}
    if action!='add': return {'ok':False,'error':'unknown_action'}
    a=r.get('amount'); c=r.get('category')
    if type(a) is not int or a<=0: return {'ok':False,'error':'invalid_amount'}
    if not isinstance(c,str) or not c.strip(): return {'ok':False,'error':'invalid_category'}
    e={'amount':a,'category':c.strip()}; entries.append(e); p.write_text(json.dumps(entries,ensure_ascii=False),encoding='utf-8')
    return {'ok':True,'entry':e}
'''
        }
        code = 'import json, sys\n' + bodies[item['id']] + "\nif __name__=='__main__':\n    print(json.dumps(handle(json.load(sys.stdin)),ensure_ascii=False))\n"
        return {'summary': '离线固定代码，无模型调用', 'files': {'main.py': code, 'README.md': '固定模拟项目，仅用于测试评测机制。'}}


def summarize(results: list[dict]) -> dict:
    projects = [r for r in results if r['expected'] == 'project']
    by_category = {}
    for category in sorted({r['category'] for r in results}):
        subset = [r for r in results if r['category'] == category]
        by_category[category] = {'success': sum(r['success'] for r in subset), 'total': len(subset)}
    return {'success': sum(r['success'] for r in results), 'total': len(results),
        'success_rate': sum(r['success'] for r in results) / len(results) if results else 0,
        'project_count': len(projects),
        'first_pass_count': sum(r['success'] and r['repair_count'] == 0 for r in projects),
        'first_pass_rate': sum(r['success'] and r['repair_count'] == 0 for r in projects) / len(projects) if projects else 0,
        'repair_count': sum(r['repair_count'] for r in projects), 'by_category': by_category}


def evaluate(client, store: RunStore, *, mode: str, selected=None, output: Path | None = None) -> dict:
    suite_bytes = SUITE.read_bytes()
    suite = json.loads(suite_bytes)
    if selected:
        unknown = set(selected) - {c['id'] for c in suite}
        if unknown:
            raise ValueError('未知评测编号：' + ', '.join(sorted(unknown)))
        suite = [c for c in suite if c['id'] in selected]
    report = {'mode': mode, 'created_at': timestamp(), 'suite_sha256': hashlib.sha256(suite_bytes).hexdigest(),
        'description': '真实模型；独立用例不传给编码或返工节点；每需求仅一次流程' if mode == 'deepseek' else '离线固定响应或故障注入：仅验证评测与流程机制，不代表模型能力',
        'results': [], 'metrics': {}}
    for item in suite:
        active_client = FixtureClient(item) if mode == 'fixture' else client
        workflow = MiniSEWorkflow(active_client, store, mode=mode)
        error = ''
        try:
            state = workflow.run(item['task'])
        except WorkflowExecutionError as exc:
            state, error = exc.state, str(exc)
        independent = None
        if item['expected'] == 'questions':
            success = state.status == 'needs_input' and bool(state.specification.get('questions')) and not state.files
        else:
            if state.files:
                independent = AcceptanceRunner().run(state.files, copy.deepcopy(item['checks']))
            success = state.status == 'approved' and bool(independent and independent['passed'])
        report['results'].append({'id': item['id'], 'category': item['category'], 'expected': item['expected'],
            'run_id': state.run_id, 'status': state.status, 'success': success, 'repair_count': state.repair_count,
            'error': error, 'independent': independent, 'questions': state.specification.get('questions', [])})
        report['metrics'] = summarize(report['results'])
        report['usage_records'] = getattr(client, 'usage_records', []) if mode != 'fixture' else []
        report['http_request_count'] = getattr(client, 'request_count', 0) if mode != 'fixture' else 0
        if output:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f"{item['id']}: {'PASS' if success else 'FAIL'} [{state.status}]", flush=True)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description='独立固定评测；默认离线机制验证。')
    parser.add_argument('--real', action='store_true')
    parser.add_argument('--cases', nargs='+')
    parser.add_argument('--output', default=str(ROOT/'outputs/evaluation-fixture.json'))
    parser.add_argument('--run-root', default=str(ROOT/'outputs'))
    parser.add_argument('--request-limit', type=int, default=30)
    parser.add_argument('--max-tokens', type=int, default=8192)
    args = parser.parse_args(argv)
    if not 1 <= args.request_limit <= 100 or not 1024 <= args.max_tokens <= 16384:
        parser.error('请求预算应为1–100，输出token预算应为1024–16384。')
    client = None
    if args.real:
        load_env(ROOT/'.env')
        client = DeepSeekClient(os.getenv('LLM_BASE_URL', 'https://api.deepseek.com'),
            os.getenv('DEEPSEEK_API_KEY') or os.getenv('LLM_API_KEY', ''), os.getenv('LLM_MODEL', 'deepseek-chat'),
            timeout_seconds=float(os.getenv('LLM_TIMEOUT_SECONDS', '90')), max_retries=int(os.getenv('LLM_MAX_RETRIES', '3')),
            thinking=os.getenv('LLM_THINKING') or None, reasoning_effort=os.getenv('LLM_REASONING_EFFORT') or None,
            max_tokens=args.max_tokens, request_limit=args.request_limit)
    report = evaluate(client, RunStore(args.run_root), mode='deepseek' if args.real else 'fixture', selected=args.cases, output=Path(args.output))
    print(json.dumps(report['metrics'], ensure_ascii=False), flush=True)
    return 0 if report['metrics']['success'] == report['metrics']['total'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
