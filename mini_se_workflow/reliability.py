"""Paired, fixed-task study of bounded planning corrections."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import time
import zipfile
from pathlib import Path

from .cli import ROOT, load_env
from .comparison import ComparisonFixtureClient, CountingClient, DevelopmentRunner, SUITE
from .llm import DeepSeekClient
from .models import WorkflowExecutionError, timestamp
from .runner import AcceptanceRunner
from .store import RunStore
from .workflow import MiniSEWorkflow


class ReliabilityFixtureClient(ComparisonFixtureClient):
    """An invalid reference followed by the normal template; never a model result."""
    def begin(self, item):
        self.task_case = item
        self.inject = True

    def complete_json(self, **kwargs):
        result = super().complete_json(**kwargs)
        if kwargs['agent_name'] == 'requirements' and self.inject:
            self.inject = False
            result['acceptance'][0]['requirement_ids'] = ['MISSING_REFERENCE']
        return result


def write_report(report: dict, output: Path) -> None:
    report['metrics'] = {}
    for arm in ('disabled', 'enabled'):
        rows = [r for r in report['trials'] if r['arm'] == arm]
        report['metrics'][arm] = {'success': sum(r['success'] for r in rows), 'total': len(rows),
            'logical_calls': sum(r['logical_calls'] for r in rows),
            'http_requests': sum(r['http_requests'] for r in rows),
            'corrections': sum(r['corrections'] for r in rows),
            'duration_seconds': round(sum(r['duration_ms'] for r in rows) / 1000, 3)}
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    lines = ['# 前置纠正实验结果', '', f"模式：{report['mode']}；完成：{len(report['trials'])}/6。", '',
        '两组使用相同模型、提示、开发集、隐藏独立集及代码返工预算，只改变需求/设计的输出纠正预算。', '',
        '| 组别 | 成功 | 逻辑调用 | HTTP请求 | 前置纠正 | 耗时（秒） |', '|---|---|---|---|---|---|']
    for arm, item in report['metrics'].items():
        lines.append(f"| {arm} | {item['success']}/{item['total']} | {item['logical_calls']} | {item['http_requests']} | {item['corrections']} | {item['duration_seconds']} |")
    lines += ['', '| 任务 | 组别 | 状态 | 独立结果 | 错误 |', '|---|---|---|---|---|']
    for trial in report['trials']:
        heldout = trial['holdout']
        result = f"{heldout['passed_count']}/{heldout['total']}" if heldout else '未执行'
        error = (trial['error'] or '无').replace('|', '/').replace('\n', ' ')
        lines.append(f"| {trial['task']} | {trial['arm']} | {trial['status']} | {result} | {error} |")
    lines += ['', '## 用量与限制', '',
        f"已记录用量：输入{report['prompt_tokens']}、输出{report['completion_tokens']} token。高峰全未缓存估算{report['recorded_cost_usd']:.6f}美元。",
        f"HTTP请求{report['http_request_count']}次，其中{report['requests_without_usage']}次无usage记录；金额不是完整账单。", '',
        '每组每任务仅一次，未固定服务随机种子，不构成统计显著或普遍能力证明。失败提前结束也包含在耗时内。',
        '本实验两组均已使用新版提示及客户端，不能将结果视为完整旧版本与新版本的因果对照。旧单/三Agent实验原样保留。',
        'fixture模式有意注入错误引用，只验证纠正机制，不衡量模型能力。独立用例不参与生成或返工反馈。',
        '随附ZIP包含实验时源文件、套件与每次流程状态、代码、日志；源码哈希按原始字节计算。', '']
    output.with_suffix('.md').write_text('\n'.join(lines), encoding='utf-8')


def study(client, store: RunStore, *, mode: str, output: Path) -> dict:
    if output.exists() or output.with_suffix('.zip').exists() or output.with_suffix('.md').exists():
        raise ValueError('实验目标已存在，请选择新路径，保留旧实验。')
    output.parent.mkdir(parents=True, exist_ok=True)
    suite_bytes = SUITE.read_bytes()
    suite = json.loads(suite_bytes)
    if [item['id'] for item in suite] != ['text-stats', 'ledger', 'library']:
        raise ValueError('固定实验必须包含文本统计、记账、图书三个任务。')
    sources = {p.name: p.read_bytes() for p in Path(__file__).parent.glob('*.py')}
    report = {'created_at': timestamp(), 'mode': mode, 'complete': False,
        'suite_sha256': hashlib.sha256(suite_bytes).hexdigest(),
        'implementation_sha256': {name: hashlib.sha256(body).hexdigest() for name, body in sources.items()},
        'settings': {key: getattr(client, key, None) for key in
                     ('model', 'thinking', 'reasoning_effort', 'max_tokens', 'request_limit', 'timeout_seconds')},
        'correction_budgets': {'disabled': 0, 'enabled': 2}, 'code_repairs': 2,
        'trials': [], 'usage_records': [], 'http_request_count': 0,
        'prompt_tokens': 0, 'completion_tokens': 0, 'recorded_cost_usd': 0, 'requests_without_usage': 0}
    tracked = CountingClient(client)
    start_requests = getattr(client, 'request_count', 0)
    start_usage = len(getattr(client, 'usage_records', []))
    write_report(report, output)
    for index, item in enumerate(suite):
        for arm in (('disabled', 'enabled') if index % 2 == 0 else ('enabled', 'disabled')):
            if mode == 'fixture':
                client.begin(item)
            before_calls = len(tracked.calls)
            before_requests = getattr(client, 'request_count', 0)
            started = time.monotonic()
            workflow = MiniSEWorkflow(tracked, store, mode=mode, max_stage_corrections=report['correction_budgets'][arm],
                                      runner=DevelopmentRunner(item['development']))
            try:
                state = workflow.run(item['task'])
            except WorkflowExecutionError as exc:
                state = exc.state
            heldout = AcceptanceRunner().run(state.files, copy.deepcopy(item['holdout'])) if state.files else None
            success = state.status == 'approved' and bool(heldout and heldout['passed'])
            state.independent_evaluation = {'case_id': item['id'], 'mode': mode, 'expected': 'project',
                'success': success, 'suite_sha256': report['suite_sha256'], 'report': heldout}
            store.save(state.to_dict())
            trial = {'task': item['id'], 'arm': arm, 'run_id': state.run_id, 'status': state.status,
                'success': success, 'error': state.error, 'holdout': heldout, 'repair_count': state.repair_count,
                'logical_calls': len(tracked.calls) - before_calls,
                'http_requests': getattr(client, 'request_count', 0) - before_requests,
                'corrections': sum(r['corrections_used'] for r in state.planning.values()),
                'planning': copy.deepcopy(state.planning), 'duration_ms': round((time.monotonic() - started) * 1000)}
            report['trials'].append(trial)
            report['usage_records'] = copy.deepcopy(getattr(client, 'usage_records', [])[start_usage:])
            report['http_request_count'] = getattr(client, 'request_count', 0) - start_requests
            report['requests_without_usage'] = report['http_request_count'] - len(report['usage_records'])
            report['prompt_tokens'] = sum(r['usage'].get('prompt_tokens', 0) for r in report['usage_records'])
            report['completion_tokens'] = sum(r['usage'].get('completion_tokens', 0) for r in report['usage_records'])
            report['recorded_cost_usd'] = (report['prompt_tokens'] * 0.30 + report['completion_tokens'] * 1.20) / 1_000_000
            report['complete'] = len(report['trials']) == 6
            write_report(report, output)
            # Rebuild from the captured bytes so later code edits cannot change this experiment's provenance.
            with zipfile.ZipFile(output.with_suffix('.zip'), 'w', zipfile.ZIP_DEFLATED) as archive:
                archive.write(output, 'result.json')
                archive.write(output.with_suffix('.md'), 'report.md')
                archive.writestr('fixtures/comparison.json', suite_bytes)
                for name, body in sources.items():
                    archive.writestr('implementation/' + name, body)
                for row in report['trials']:
                    directory = store.directory(row['run_id'])
                    for path in sorted(directory.rglob('*')):
                        if path.is_symlink():
                            raise ValueError('归档不能包含符号链接。')
                        if path.is_file():
                            archive.write(path, 'runs/' + row['run_id'] + '/' + path.relative_to(directory).as_posix())
            print(f"{item['id']} {arm}: {'PASS' if success else 'FAIL'}; corrections={trial['corrections']}; {state.error}", flush=True)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description='固定三任务、每组一次的前置纠正实验；默认离线故障注入。')
    parser.add_argument('--real', action='store_true')
    parser.add_argument('--output')
    parser.add_argument('--run-root', default=str(ROOT / 'outputs/reliability/runs'))
    args = parser.parse_args(argv)
    client = ReliabilityFixtureClient()
    if args.real:
        load_env(ROOT / '.env')
        client = DeepSeekClient(os.getenv('LLM_BASE_URL', 'https://api.deepseek.com'),
            os.getenv('DEEPSEEK_API_KEY') or os.getenv('LLM_API_KEY', ''), os.getenv('LLM_MODEL', 'deepseek-flash'),
            thinking=os.getenv('LLM_THINKING') or None, reasoning_effort=os.getenv('LLM_REASONING_EFFORT') or None,
            timeout_seconds=90, max_retries=3, max_tokens=16384, request_limit=60)
    output = Path(args.output or ROOT / ('outputs/reliability-real.json' if args.real else 'outputs/reliability-fixture.json'))
    report = study(client, RunStore(args.run_root), mode='deepseek' if args.real else 'fixture', output=output)
    print(json.dumps(report['metrics'], ensure_ascii=False), flush=True)
    return 0 if report['complete'] and report['metrics']['enabled']['success'] == 3 else 2


if __name__ == '__main__':
    raise SystemExit(main())
