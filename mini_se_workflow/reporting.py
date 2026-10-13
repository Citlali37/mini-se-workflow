from __future__ import annotations

import difflib
from collections import defaultdict


def revision_diffs(state: dict) -> list[dict]:
    result, previous = [], {}
    for revision in state.get('iterations', []):
        current = revision.get('files', {})
        changes = []
        # Invalid output isn't a real empty project version. Preserve the last valid baseline.
        if current:
            for name in sorted(set(previous) | set(current)):
                if previous.get(name) != current.get(name):
                    patch = ''.join(difflib.unified_diff(previous.get(name, '').splitlines(keepends=True),
                        current.get(name, '').splitlines(keepends=True), fromfile='before/'+name, tofile='after/'+name))
                    changes.append({'file': name, 'kind': 'added' if name not in previous else ('deleted' if name not in current else 'modified'), 'diff': patch})
            previous = current
        validation = revision.get('validation', {})
        result.append({'revision': revision['revision'], 'changes': changes,
            'reason': validation.get('error', ''), 'failed_cases': [c['id'] for c in validation.get('cases', []) if not c['passed']]})
    return result


def delivery_report(state: dict) -> str:
    spec = state.get('confirmed_specification') or state.get('specification', {})
    lines = ['# Mini SE 交付报告', '', f"运行编号：{state['run_id']}", f"状态：{state['status']}",
        f"模式：{state['mode']}", f"已返工：{state.get('repair_count', 0)} / {state.get('max_repairs', 2)}", '',
        '## 原始需求与补充', '', state.get('task', ''), '', '## 需求确认记录', '',
        f"确认时间：{state.get('confirmed_at') or '旧记录或尚未确认'}",
        f"规格修改/补充记录：{len(state.get('requirement_history', []))} 条", '', '## 需求追踪', '']
    for requirement in spec.get('requirements', []):
        key = requirement['id']
        files = [f['path'] for f in state.get('design', {}).get('files', []) if key in f.get('requirement_ids', [])]
        cases = [c['id'] for c in spec.get('acceptance', []) if key in c.get('requirement_ids', [])]
        lines.append(f"- {key}：{requirement['description']}；文件：{', '.join(files) or '未设计'}；验收：{', '.join(cases) or '无'}")
    lines += ['', '## 每版验收与修改', '']
    diffs = revision_diffs(state)
    for revision, changes in zip(state.get('iterations', []), diffs):
        validation = revision['validation']
        lines += [f"### 第 {revision['revision']+1} 版", '', revision.get('summary', ''),
            f"结果：{validation['passed_count']}/{validation['total']}；{'通过' if validation['passed'] else '未通过'}",
            f"失败原因：{changes['reason'] or ', '.join(changes['failed_cases']) or '无'}", '']
        for case in validation.get('cases', []):
            if not case['passed']:
                for step in case['steps']:
                    if not step['passed']:
                        lines.append(f"- {case['id']}：{step.get('difference') or step.get('error')}")
        for change in changes['changes']:
            lines += ['', f"文件：{change['file']}（{change['kind']}）", '```diff', change['diff'].rstrip(), '```']
    durations = defaultdict(int)
    for e in state.get('events', []):
        if 'duration_ms' in e:
            durations[e['agent']] += e['duration_ms']
    lines += ['', '## 已记录阶段耗时', '']
    lines += [f'- {agent}：{value} ms' for agent, value in durations.items()]
    lines += ['', '## 限制与解释', '',
        '通过只表示满足当前验收集，不保证所有输入正确。独立评测结果应另行查看。',
        '模型生成的需求及用例可能遗漏用户意图；需求编号关联用于追踪，不能证明语义正确。',
        '执行使用本机 Python，范围检查不是操作系统级沙箱。',
        '取消与恢复以节点/检查点为单位；不能恢复某个模型请求内部的执行。',
        f"未恢复异常：{state.get('error') or '无'}", '']
    return '\n'.join(lines)
