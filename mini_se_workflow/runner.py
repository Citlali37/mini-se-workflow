from __future__ import annotations

import ast
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Callable
from .models import WorkflowCancelled
from .contracts import file_path


ALLOWED_IMPORTS = {
    "json", "sys", "pathlib", "dataclasses", "math", "re", "collections", "itertools",
    "functools", "datetime", "decimal", "statistics", "typing", "enum", "string",
    "random", "heapq", "bisect", "csv", "io", "__future__",
}
FORBIDDEN_NAMES = {"eval", "exec", "compile", "__import__", "breakpoint", "globals", "locals", "vars", "getattr", "setattr", "delattr"}
FORBIDDEN_ATTRIBUTES = {"modules", "__dict__", "__class__", "__subclasses__", "__globals__", "__builtins__", "__getattribute__"}
MAX_OUTPUT = 65536


def validate_fixtures(files: dict, cases: list[dict]) -> None:
    """Only trusted independent tests use setup/preservation metadata; model contracts strip it."""
    source_names = {name.lower() for name in files}
    def checked(name, directory=False):
        base = name[:-4] if isinstance(name, str) and directory and name.endswith('.tmp') else name
        file_path(base)
        if not base.endswith(('.json', '.txt')) or name.lower() in source_names:
            raise ValueError('测试夹具只能使用不覆盖源文件的根目录JSON/TXT数据文件。')
    for case in cases:
        initial = case.get('initial_files', {})
        directories = case.get('initial_directories', [])
        if not isinstance(initial, dict) or len(initial) > 10 or not isinstance(directories, list) or len(directories) > 10:
            raise ValueError('测试夹具数量无效。')
        for name, body in initial.items():
            checked(name)
            if not isinstance(body, str) or len(body.encode('utf-8')) > 100000:
                raise ValueError('测试夹具内容无效或超过100KB。')
        for name in directories:
            checked(name, directory=True)
        if {n.lower() for n in directories} & {n.lower() for n in initial}:
            raise ValueError('文件与目录夹具不能重叠。')
        for step in case['steps']:
            preserve = step.get('preserve_files', [])
            if not isinstance(preserve, list) or len(preserve) > 10:
                raise ValueError('文件保留断言无效。')
            for name in preserve:
                checked(name)


def file_snapshot(path: Path) -> dict:
    if not path.exists():
        return {'kind': 'missing'}
    if path.is_dir():
        return {'kind': 'directory'}
    size = path.stat().st_size
    if size > 1000000:
        raise ValueError('待核验数据文件超过1MB。')
    return {'kind': 'file', 'bytes': size, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def source_checks(files: dict[str, str]) -> list[dict]:
    """Conservative checks for the small-tool scope; this is not an OS sandbox."""
    checks = []
    local = {Path(name).stem for name in files if name.endswith(".py")}
    for name, source in files.items():
        if not name.endswith(".py"):
            continue
        errors = []
        try:
            tree = ast.parse(source, filename=name)
            compile(tree, name, "exec")
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    if any(n.name.split(".")[0] not in ALLOWED_IMPORTS | local for n in node.names):
                        errors.append(f"第 {node.lineno} 行包含范围外的导入。")
                elif isinstance(node, ast.ImportFrom):
                    if node.level or not node.module or node.module.split(".")[0] not in ALLOWED_IMPORTS | local:
                        errors.append(f"第 {node.lineno} 行包含范围外的导入。")
                elif isinstance(node, ast.Name) and node.id in FORBIDDEN_NAMES | {"__builtins__"}:
                    errors.append(f"第 {node.lineno} 行使用了不支持的动态执行能力。")
                elif isinstance(node, ast.Attribute) and node.attr in FORBIDDEN_ATTRIBUTES:
                    errors.append(f"第 {node.lineno} 行包含不支持的运行时访问。")
        except SyntaxError as exc:
            errors.append(f"第 {exc.lineno} 行语法错误：{exc.msg}")
        checks.append({"file": name, "passed": not errors, "errors": list(dict.fromkeys(errors))})
    return checks


def compare_json(actual: object, expected: object, path: str = "$") -> str | None:
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return f"{path} 应为对象。"
        for key, value in expected.items():
            if key not in actual:
                return f"{path} 缺少字段 {key}。"
            difference = compare_json(actual[key], value, f"{path}.{key}")
            if difference:
                return difference
        return None
    if isinstance(expected, list):
        if not isinstance(actual, list) or len(actual) != len(expected):
            return f"{path} 数组长度不符合预期。"
        for index, (value, target) in enumerate(zip(actual, expected)):
            difference = compare_json(value, target, f"{path}[{index}]")
            if difference:
                return difference
        return None
    # JSON true must not compare equal to numeric 1.
    if isinstance(expected, bool) != isinstance(actual, bool) or actual != expected:
        return f"{path} 预期 {expected!r}，实际 {actual!r}。"
    return None


def stop_process(process: subprocess.Popen) -> None:
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=5, creationflags=subprocess.CREATE_NO_WINDOW,
        )
    else:
        process.kill()
    if process.poll() is None:
        process.kill()
    process.wait(timeout=5)


def execute_request(root: Path, request: dict, timeout: float, should_cancel=None) -> dict:
    env = {key: os.environ[key] for key in ("SystemRoot", "WINDIR") if key in os.environ}
    env.update({"TEMP": str(root), "TMP": str(root), "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"})
    start = time.monotonic()
    with tempfile.TemporaryFile() as input_file, tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        input_file.write(json.dumps(request, ensure_ascii=False, allow_nan=False).encode("utf-8"))
        input_file.seek(0)
        process = subprocess.Popen(
            [sys.executable, "-X", "utf8", "-B", "-s", "-E", "main.py"],
            cwd=root, env=env, stdin=input_file, stdout=stdout, stderr=stderr,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        error = ""
        try:
            while process.poll() is None:
                if should_cancel and should_cancel():
                    raise WorkflowCancelled("用户取消了验收。")
                if time.monotonic() - start > timeout:
                    error = f"执行超时（{timeout:.1f} 秒）。"
                    stop_process(process)
                    break
                if os.fstat(stdout.fileno()).st_size + os.fstat(stderr.fileno()).st_size > MAX_OUTPUT:
                    error = "程序输出超过 64 KB。"
                    stop_process(process)
                    break
                time.sleep(0.02)
        finally:
            if process.poll() is None:
                stop_process(process)
        oversized = os.fstat(stdout.fileno()).st_size + os.fstat(stderr.fileno()).st_size > MAX_OUTPUT
        stdout.seek(0)
        stderr.seek(0)
        output = stdout.read(MAX_OUTPUT).decode("utf-8", errors="replace")
        diagnostic = stderr.read(MAX_OUTPUT).decode("utf-8", errors="replace")
        actual = None
        if oversized:
            error = error or "程序输出超过 64 KB。"
        if not error and process.returncode != 0:
            error = f"程序退出码为 {process.returncode}。"
        if not error:
            try:
                actual = json.loads(output, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
                if not isinstance(actual, dict):
                    error = "stdout 必须是单个 JSON 对象。"
            except (json.JSONDecodeError, ValueError, RecursionError):
                error = "stdout 不是有效的单个 JSON 对象。"
        return {"actual": actual, "stdout": output[:8000], "stderr": diagnostic[:8000], "exit_code": process.returncode, "error": error, "duration_ms": round((time.monotonic() - start) * 1000)}


class AcceptanceRunner:
    def __init__(self, step_timeout: float = 5, round_timeout: float = 60) -> None:
        if not 0.1 <= step_timeout <= 30 or not 1 <= round_timeout <= 180:
            raise ValueError("执行超时参数超出范围。")
        self.step_timeout = step_timeout
        self.round_timeout = round_timeout

    def case_count(self, cases: list[dict]) -> int:
        return len(cases)

    def run(self, files: dict[str, str], cases: list[dict], on_case: Callable[[dict], None] | None = None, *, should_cancel=None) -> dict:
        validate_fixtures(files, cases)
        syntax = source_checks(files)
        report = {"passed": False, "source_checks": syntax, "cases": [], "total": len(cases), "passed_count": 0}
        if not syntax or any(not item["passed"] for item in syntax):
            report["error"] = "源代码检查未通过，尚未执行程序。"
            return report
        deadline = time.monotonic() + self.round_timeout
        for case in cases:
            if should_cancel and should_cancel():
                raise WorkflowCancelled("用户取消了验收。")
            result = {"id": case["id"], "source": case.get("source", "requirements"), "description": case["description"], "requirement_ids": case.get("requirement_ids", []), "passed": True, "steps": []}
            # Every test starts from a clean project. Each step restarts main.py in the same directory.
            with tempfile.TemporaryDirectory(prefix="mini-se-check-") as temp:
                root = Path(temp)
                for name, content in files.items():
                    (root / name).write_text(content, encoding="utf-8")
                for name, content in case.get('initial_files', {}).items():
                    (root / name).write_text(content, encoding='utf-8')
                for name in case.get('initial_directories', []):
                    (root / name).mkdir()
                for index, step in enumerate(case["steps"], 1):
                    before = {name: file_snapshot(root / name) for name in step.get('preserve_files', [])}
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        execution = {"actual": None, "error": "本轮验收时间预算已用完。", "stdout": "", "stderr": ""}
                    else:
                        execution = execute_request(root, step["input"], min(self.step_timeout, remaining), should_cancel)
                    difference = execution["error"] or compare_json(execution["actual"], step["expected"])
                    file_checks = []
                    for name, original in before.items():
                        after = file_snapshot(root / name)
                        unchanged = original == after
                        file_checks.append({'file': name, 'passed': unchanged, 'before': original, 'after': after})
                        if not unchanged:
                            difference = difference or f'失败请求改变了数据文件 {name}。'
                    if file_checks:
                        execution['file_checks'] = file_checks
                    result["steps"].append({"number": index, "input": step["input"], "expected": step["expected"], **execution, "passed": not difference, "difference": difference or ""})
                    if difference:
                        result["passed"] = False
                        break
            report["cases"].append(result)
            report["passed_count"] += int(result["passed"])
            if on_case:
                on_case(result)
        report["passed"] = report["passed_count"] == report["total"] and report["total"] > 0
        return report
