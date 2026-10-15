from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
from uuid import uuid4

from .cli import ROOT
from .models import timestamp, WorkflowState
from .runner import AcceptanceRunner
from .contracts import specification, design
from .store import RunStore


CASES = Path(__file__).with_name('fixtures') / 'library-checks.json'


def suite_hash() -> str:
    # Canonical JSON avoids Windows CRLF vs Linux LF invalidating the same test content.
    body = json.dumps(json.loads(CASES.read_text(encoding='utf-8-sig')),ensure_ascii=False,sort_keys=True,separators=(',',':'))
    return hashlib.sha256(body.encode('utf-8')).hexdigest()


def load_files(root: Path) -> dict[str, str]:
    return {p.name: p.read_text(encoding='utf-8-sig') for p in sorted(root.iterdir()) if p.is_file() and p.suffix in {'.py', '.md'}}


def files_hash(files: dict) -> str:
    return hashlib.sha256(json.dumps(files, ensure_ascii=False, sort_keys=True).encode('utf-8')).hexdigest()


def audit(output: Path | None = None) -> dict:
    source = ROOT / 'examples/library-audit'
    snapshot = json.loads((source/'original-workflow.json').read_text(encoding='utf-8'))
    cases = json.loads(CASES.read_text(encoding='utf-8'))
    result = {'created_at': timestamp(), 'source_run_id': snapshot['run_id'],
        'suite_sha256': suite_hash(), 'suite_hash_format':'canonical JSON, UTF-8, sorted keys, compact separators',
        'description': '原始模型产物与人工审查修订版分别记录；新增规则不回填为原验收失败。', 'versions': {}}
    for name in ('original', 'reviewed'):
        files = load_files(source/name)
        if name == 'original' and files != snapshot['files']:
            raise ValueError('原始快照与原始源文件不一致。')
        runner = AcceptanceRunner()
        regression = runner.run(files, snapshot['specification']['acceptance'])
        independent = runner.run(files, cases)
        groups = {}
        for group in sorted({c['group'] for c in cases}):
            ids = {c['id'] for c in cases if c['group'] == group}
            checks = [c for c in independent['cases'] if c['id'] in ids]
            groups[group] = {'passed': sum(c['passed'] for c in checks), 'total': len(ids)}
        result['versions'][name] = {'provenance': '原始真实模型生成' if name == 'original' else '人工审查修订，非模型自动返工',
            'files_sha256': files_hash(files), 'regression': regression, 'independent': independent, 'groups': groups}
        print(name, 'regression', f"{regression['passed_count']}/{regression['total']}",
            'independent', f"{independent['passed_count']}/{independent['total']}", flush=True)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return result


def publish_reviewed(result: dict, store: RunStore) -> WorkflowState:
    """New, explicitly human-reviewed run. Never overwrite the original model generation."""
    root = ROOT/'examples/library-audit'
    original = json.loads((root/'original-workflow.json').read_text(encoding='utf-8'))
    original_files = load_files(root/'original')
    if original_files != original['files'] or files_hash(original_files) != result['versions']['original']['files_sha256']:
        raise ValueError('原始快照或源文件已变化，必须重新审查。')
    reviewed = result['versions']['reviewed']
    if result['suite_sha256'] != suite_hash():
        raise ValueError('独立套件已变化，必须重新审查。')
    files = load_files(root/'reviewed')
    if files_hash(files) != reviewed['files_sha256'] or not reviewed['regression']['passed'] or not reviewed['independent']['passed']:
        raise ValueError('修订版尚未通过验证，不能发布为通过。')
    spec = copy.deepcopy(original['specification'])
    spec['project_name'] += '（人工审查修订版）'
    spec['summary'] += ' 本版由人工审查修订，补充必填字段及存储保护，不代表Agent自动返工。'
    for requirement in spec['requirements']:
        if requirement['id']=='R1':
            requirement['description'] += ' title必须为非空白字符串，去除首尾空白；否则invalid_title。'
        elif requirement['id']=='R2':
            requirement['description'] += ' name必须为非空白字符串，去除首尾空白；否则invalid_name。'
        elif requirement['id']=='R10':
            requirement['description'] += ' 损坏、结构非法、读取或写入失败时返回storage_error并保留旧文件；使用同目录临时文件替换保存。'
        elif requirement['id']=='R11':
            requirement['description'] += ' 拒绝纯空白编号；日期加14天溢出返回invalid_date。'
    spec['acceptance'].append({'id':'A9','description':'质量补充：必填书名和姓名不能省略或为空白','requirement_ids':['R1','R2','R11'],
        'steps':[{'input':{'action':'add_book','book_id':'X','total_copies':1},'expected':{'ok':False,'error':'invalid_title'}},
                 {'input':{'action':'add_reader','reader_id':'X','name':'  '},'expected':{'ok':False,'error':'invalid_name'}}]})
    spec = specification(spec)
    plan = {'summary':'人工审查保留原模块划分，修正原设计中的宽松校验和损坏文件重置策略。',
        'files':copy.deepcopy(original['design']['files']),
        'interfaces':[
            '沿用原始六个JSON动作及响应结构；原始8项验收继续满足。',
            'add_book必须校验title，add_reader必须校验name，拒绝缺失、非文本和纯空白值。',
            'validators校验非空白编号、严格日期及借阅期限日期溢出；不额外限制合法还书日期与借阅日期先后。',
            'storage.load_library只对FileNotFoundError初始化；现有文件损坏、结构错误或不可读抛出StorageError。',
            'storage.save_library写入library_data.json.tmp并Path.replace；写入失败抛出StorageError并保留旧数据。',
            'main捕获StorageError，返回单JSON {ok:false,error:storage_error}，退出0；不返回虚假的成功。'],
        'data_model':'沿用next_seq、books、readers、borrows结构；加载时检查类型、引用、序号、日期及库存约束，不静默重建。'}
    for f in plan['files']:
        if f['path']=='storage.py': f['purpose']='严格加载、保留损坏文件、以同目录临时文件替换保存。'
        elif f['path']=='validators.py': f['purpose']='编号、整数、日期校验及日期溢出处理。'
    plan = design(plan,spec)
    state = WorkflowState(uuid4().hex[:16],original['task']+'\n\n质量补充：必填字段严格校验；存储异常保留原数据并报错。',
        'human_reviewed',status='approved',current_step='done',next_step='done',max_repairs=1,repair_count=1,
        specification=spec,confirmed_specification=copy.deepcopy(spec),confirmed_at=timestamp(),design=plan,files=files)
    state.requirement_history=[{'time':timestamp(),'action':'source_snapshot','source_run_id':original['run_id']},
        {'time':timestamp(),'action':'quality_amendment','specification':copy.deepcopy(spec),
         'note':'新运行采用补充规格；原始运行及8/8验收不变。两版均按同一补充规格重新验收。'}]
    for revision, (version, description) in enumerate((('original','原始模型产物按新增规格复验'),('reviewed','人工审查修订；没有模型API调用'))):
        body = load_files(root/version)
        validation = AcceptanceRunner().run(body,spec['acceptance'])
        state.iterations.append({'revision':revision,'summary':description,'files':body,'validation':validation})
        store.revision(state.run_id,revision,body,validation)
    if not state.iterations[-1]['validation']['passed']:
        raise ValueError('补充规格回归失败，不能发布。')
    state.independent_evaluation={'case_id':'library-audit','mode':'human_reviewed','expected':'project','success':True,
        'suite_sha256':result['suite_sha256'],'report':copy.deepcopy(reviewed['independent'])}
    messages=['原始生成记录 '+original['run_id']+' 保持不变；本记录为人工审查修订。',
              '独立检查原版9/21、修订版21/21；新增质量规则与原需求分别记录。',
              '补充规格下重新检查两版；可查看代码差异和下载修订版。']
    for i,message in enumerate(messages,1):
        state.events.append({'sequence':i,'time':timestamp(),'step':'done','agent':'人工审查','status':'completed','message':message})
    store.save(state.to_dict())
    return state


def main(argv=None):
    parser = argparse.ArgumentParser(description='复现图书案例缺陷，并检查人工修订版；不调用模型。')
    parser.add_argument('--output', default=str(ROOT/'outputs/library-audit.json'))
    parser.add_argument('--publish',action='store_true',help='在历史记录中新增明确标注的人工修订版。')
    args = parser.parse_args(argv)
    result = audit(Path(args.output))
    if args.publish:
        state=publish_reviewed(result,RunStore(ROOT/'outputs'))
        (ROOT/'examples/library-reviewed.zip').write_bytes(RunStore(ROOT/'outputs').archive(state.run_id))
        from .reporting import delivery_report
        (ROOT/'examples/library-audit/reviewed-report.md').write_text(delivery_report(state.to_dict()),encoding='utf-8')
        print('published human-reviewed run:',state.run_id,flush=True)
    reviewed = result['versions']['reviewed']
    return 0 if reviewed['regression']['passed'] and reviewed['independent']['passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
