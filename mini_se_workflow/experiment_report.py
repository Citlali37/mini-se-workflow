from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from collections import Counter
from pathlib import Path

from .cli import ROOT
from .store import RunStore


def export(path: Path, store: RunStore) -> tuple[Path, Path]:
    report=json.loads(path.read_text(encoding='utf-8'))
    complete=len(report['trials'])==len(report['order'])
    lines=['# 单 Agent / 三 Agent 对照结果','',f"模式：{report['mode']}；{'已完成全部预注册流程' if complete else '尚未完成'}。",
        '三个任务、每方案两次重复，失败保留在分母。开发与独立测试、执行器、返工次数和模型配置相同。','',
        '| 方案 | 成功 | 初稿成功 | 逻辑调用 / HTTP请求 | 总耗时（秒） | 输入 / 输出tokens | 已记录用量按高峰无缓存估算（元） |',
        '|---|---|---|---|---|---|---|']
    for arm,label in (('single','单Agent'),('multi','三Agent')):
        m=report['metrics'][arm]
        lines.append(f"| {label} | {m['success']}/{m['trials']} | {m['first_pass_success']}/{m['trials']} | {m['logical_calls']} / {m['http_requests']} | {m['duration_ms']/1000:.1f} | {m['prompt_tokens']} / {m['completion_tokens']} | {m['recorded_cost_peak_uncached_cny']:.4f} |")
    lines+=['','## 分任务结果','','| 任务 | 单Agent成功 | 三Agent成功 |','|---|---|---|']
    for task in dict.fromkeys(t['task'] for t in report['trials']):
        counts=[]
        for arm in ('single','multi'):
            rows=[t for t in report['trials'] if t['task']==task and t['arm']==arm]
            counts.append(f"{sum(t['success'] for t in rows)}/{len(rows)}")
        lines.append(f"| {task} | {' | '.join(counts)} |")
    lines+=['','## 全部运行','','| 次数 | 任务 | 方案 | 结果 | 返工 | 错误 |','|---|---|---|---|---|---|']
    for t in report['trials']:
        message=t['error'].replace('|','/').replace('\n',' ') or ('无' if t['success'] else '独立验收未通过')
        lines.append(f"| {t['repeat']} | {t['task']} | {t['arm']} | {'通过' if t['success'] else '未通过'} | {t['repair_count']} | {message} |")
    failures=Counter(t['error'] or '独立检查未通过' for t in report['trials'] if not t['success'])
    lines+=['','## 失败与解释','']+[f'- {error}：{count}次。' for error,count in failures.items()]
    single,multi=report['metrics']['single'],report['metrics']['multi']
    if report['mode']!='deepseek':
        observation='本报告为离线模拟，仅检查实验机制，不能据此判断模型能力。'
    elif single['success_rate']>multi['success_rate']:
        observation='本次当前实现下，单Agent观察到更高成功率；不证明单Agent普遍优于多Agent。'
    elif single['success_rate']<multi['success_rate']:
        observation='本次当前实现下，三Agent观察到更高成功率；不证明三Agent普遍优于单Agent。'
    else:
        observation='本次两种方案观察到相同成功率；不能据此认定两种方案等价。'
    lines+=['',observation,
        '三Agent的额外需求/设计契约增加了前置失败点，分工并未自动带来质量收益。对外应保留“阶段产物可审查、需求追踪与恢复”的价值，但不能宣称已证明成功率更高。',
        '需求契约或模型JSON输出阶段的前置失败不能由当前编码返工循环修复。'+('本次没有触发代码返工，不能用本实验判断返工机制的收益。' if single['repair_count']+multi['repair_count']==0 else '返工次数与结果见上表。'),
        '下一步优先考虑需求阶段的有预算格式纠正、输出长度控制与覆盖检查可诊断性；如实施，需作为新版本另做实验，不能更改本次成绩。',
        '', '## 复核与限制','',
        '- 每任务仅2次重复，未固定服务随机种子，缓存、网络和先后次序会影响结果，不能声称统计显著。',
        '- 时间包含失败提前停止和本地验收；更短的失败时间不代表成功生成更快。客户端60秒是网络读写超时，服务持续传输时不等于整次调用60秒墙钟上限。',
        '- token来自服务返回usage；有HTTP请求没有可记录usage时，金额不是完整账单。高峰无缓存估算采用每百万输入2元、输出8元，官方来源见预注册方案。',
        '- 金额列仅按预注册的Flash价格折算，换模型或价格变化后必须重新配置口径，不能沿用为实际费用。',
        '- 图书任务使用公开的严格补充协议和固定存储格式，与原始较简短需求不同，不能把这里失败回填成原8/8验收失败。',
        '- 人工修订的图书代码不参与真实模型评分，离线模板只检验实验机制。',
        '- 实现和套件SHA是实验时工作树的原始字节指纹；Windows换行可能与Git规范化文件不同。随附ZIP保留匹配指纹的原始实现和套件，另有每次运行及版本代码。','']
    markdown=path.with_suffix('.md')
    markdown.write_text('\n'.join(lines),encoding='utf-8')
    archive_path=path.with_suffix('.zip')
    verified={}
    with zipfile.ZipFile(archive_path,'w',zipfile.ZIP_DEFLATED) as archive:
        archive.write(path,'comparison.json')
        archive.write(markdown,'report.md')
        suite=Path(__file__).with_name('fixtures')/'comparison.json'
        verified['suite']=hashlib.sha256(suite.read_bytes()).hexdigest()==report['suite_sha256']
        if verified['suite']: archive.write(suite,'fixtures/comparison.json')
        for name,expected in report.get('implementation_sha256',{}).items():
            source=Path(__file__).parent/name
            verified[name]=hashlib.sha256(source.read_bytes()).hexdigest()==expected
            if verified[name]:archive.write(source,'implementation/'+name)
        for trial in report['trials']:
            directory=store.directory(trial['run_id'])
            for source in sorted(directory.rglob('*')):
                if source.is_symlink():raise ValueError('运行归档不能包含符号链接。')
                if source.is_file():archive.write(source,'runs/'+trial['run_id']+'/'+source.relative_to(directory).as_posix())
        archive.writestr('source-verification.json',json.dumps(verified,ensure_ascii=False,indent=2))
    return markdown,archive_path


def main(argv=None):
    parser=argparse.ArgumentParser(description='从已有结果导出对照报告与原始运行归档，不调用模型。')
    parser.add_argument('report')
    parser.add_argument('--run-root',default=str(ROOT/'outputs/comparison/runs'))
    args=parser.parse_args(argv)
    for output in export(Path(args.report),RunStore(args.run_root)):print(output)
    return 0


if __name__=='__main__':raise SystemExit(main())
