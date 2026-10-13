from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .demo import DEMO_TASK, DemoClient
from .llm import DeepSeekClient
from .models import WorkflowExecutionError
from .store import RunStore
from .web import run_web
from .workflow import MiniSEWorkflow


ROOT = Path(__file__).resolve().parent.parent


def load_env(path: Path) -> None:
    if path.is_file():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def create_workflow(args) -> MiniSEWorkflow:
    load_env(ROOT / ".env")
    if args.demo:
        client = DemoClient()
    else:
        key = os.getenv("DEEPSEEK_API_KEY") or os.getenv("LLM_API_KEY", "")
        if not key or key.startswith("replace-with-"):
            raise ValueError("请复制 .env.example 为 .env 并填写 DeepSeek 密钥，或运行离线演示启动脚本。")
        client = DeepSeekClient(
            base_url=os.getenv("LLM_BASE_URL", "https://api.deepseek.com"),
            api_key=key,
            model=os.getenv("LLM_MODEL", "deepseek-chat"),
            timeout_seconds=float(os.getenv("LLM_TIMEOUT_SECONDS", "90")),
            max_retries=int(os.getenv("LLM_MAX_RETRIES", "3")),
            thinking=os.getenv("LLM_THINKING") or None,
            reasoning_effort=os.getenv("LLM_REASONING_EFFORT") or None,
        )
    return MiniSEWorkflow(client, RunStore(args.output), mode="demo" if args.demo else "deepseek", max_repairs=args.max_repairs)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="需求、设计、编码三个 Agent 协作，实际执行验收并返工。")
    parser.add_argument("--demo", action="store_true", help="离线演示预置待办事项项目。")
    parser.add_argument("--web", action="store_true", help="启动本地 Web 界面。")
    parser.add_argument("--open-browser", action="store_true")
    parser.add_argument("--port", type=int, default=8002)
    parser.add_argument("--task", help="软件需求。")
    parser.add_argument("--task-file", help="从 UTF-8 文本文件读取需求。")
    parser.add_argument("--example", choices=["todo"], help="使用示例需求及独立固定验收。")
    parser.add_argument("--output", default=str(ROOT / "outputs"), help="运行记录及项目输出目录。")
    parser.add_argument("--max-repairs", type=int, choices=range(6), default=2)
    parser.add_argument("--review", action="store_true", help="在需求确认前暂停。")
    parser.add_argument("--resume", help="继续已有运行编号。")
    parser.add_argument("--action", choices=["retry", "confirm", "clarify"], default="retry")
    parser.add_argument("--spec-file", help="确认时使用修改后的规格 JSON。")
    parser.add_argument("--answer", default="", help="补充待确认问题的答案。")
    parser.add_argument("--export", help="命令行运行后把项目打包到指定 ZIP 路径。")
    args = parser.parse_args(argv)
    if args.open_browser and not args.web:
        parser.error("--open-browser 需要 --web。")
    if args.web and any((args.task, args.task_file, args.example, args.export, args.resume, args.review, args.spec_file, args.answer)):
        parser.error("Web 模式请在页面输入需求。")
    if sum(bool(v) for v in (args.task, args.task_file, args.example, args.resume)) > 1:
        parser.error("--task、--task-file、--example 只能选一个。")
    if not 0 <= args.port <= 65535:
        parser.error("端口必须在0到65535之间。")
    if (args.spec_file or args.answer or args.action != "retry") and not args.resume:
        parser.error("--action、--spec-file、--answer 需要 --resume。")
    if not args.web and not any((args.task, args.task_file, args.example, args.demo, args.resume)):
        parser.error("请提供 --task、--task-file 或 --example todo。")
    try:
        workflow = create_workflow(args)
        if args.web:
            run_web(workflow, args.port, args.open_browser)
            return 0
        task = args.task or (Path(args.task_file).read_text(encoding="utf-8-sig") if args.task_file else DEMO_TASK)
        previous = 0

        def display(state):
            nonlocal previous
            for event in state["events"][previous:]:
                print(f"[{event['sequence']}] {event['agent']}：{event['message']}", flush=True)
            previous = len(state["events"])

        if args.resume:
            import json
            spec = json.loads(Path(args.spec_file).read_text(encoding="utf-8-sig")) if args.spec_file else None
            state = workflow.resume(args.resume, action=args.action, specification=spec, answer=args.answer, on_update=display)
        else:
            state = workflow.run(task, example_id="todo" if args.example or (args.demo and task.strip() == DEMO_TASK) else None,
                                 on_update=display, require_confirmation=args.review)
        print(f"\n运行编号：{state.run_id}\n最终状态：{state.status}\n输出目录：{workflow.store.directory(state.run_id)}")
        for question in state.specification.get("questions", []):
            print(f"待确认：{question}")
        if args.export and state.files:
            target = Path(args.export).resolve()
            if target.exists():
                raise ValueError("导出文件已存在，请指定新的 ZIP 文件名。")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(workflow.store.archive(state.run_id))
            print(f"项目压缩包：{target}")
        return 0 if state.status == "approved" else 2
    except (WorkflowExecutionError, ValueError, OSError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
