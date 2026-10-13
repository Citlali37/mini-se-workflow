from __future__ import annotations

import copy
import json
from pathlib import Path

from .llm import LLMError


DEMO_TASK = (
    "开发一个待办事项工具：支持新增、查看、完成和删除任务；使用本地 JSON 文件保存，重启后数据不丢失；"
    "任务编号从1递增且不复用，标题去除首尾空白，空标题和非文本标题都应拒绝。"
    "JSON 请求使用 action 字段：add 携带 title，list 查看列表，complete/delete 携带正整数 id（布尔值不算整数）。"
    "新增和完成成功返回 ok:true,task:{id,title,completed}；查看返回 ok:true,tasks 数组（按创建顺序）；"
    "删除返回 ok:true,deleted_id。新任务 completed 为 false，完成后为 true。"
    "失败返回 ok:false,error：空白或非文本标题为 empty_title，非法编号为 invalid_id，"
    "不存在的任务为 not_found，未知操作为 unknown_action。"
)


def step(request: dict, expected: dict) -> dict:
    return {"input": request, "expected": expected}


def case(key: str, refs: list[str], description: str, *steps: dict) -> dict:
    return {"id": key, "requirement_ids": refs, "description": description, "steps": list(steps)}


def todo_specification() -> dict:
    return {
        "project_name": "待办事项管理工具",
        "summary": "通过 JSON 请求管理任务，使用本地文件持久保存；每个请求独立启动进程。",
        "assumptions": ["单用户本地使用，不需要并发操作。", "任务按照创建顺序返回，编号为正整数。"],
        "questions": [],
        "requirements": [
            {"id": "R1", "description": "新增任务并分配从1开始递增的编号，标题去除首尾空白。"},
            {"id": "R2", "description": "查看任务列表，重启后保留全部数据。"},
            {"id": "R3", "description": "按编号完成任务，修改结果持久保存。"},
            {"id": "R4", "description": "按编号删除任务，编号不复用。"},
            {"id": "R5", "description": "拒绝空白或非文本标题、非法编号、不存在的任务及未知操作，并返回约定的错误标识。"},
        ],
        "acceptance": [
            case("A1", ["R1", "R2"], "新增并在新进程中查看", step({"action": "add", "title": "写作业"}, {"ok": True, "task": {"id": 1, "title": "写作业", "completed": False}}), step({"action": "list"}, {"ok": True, "tasks": [{"id": 1, "title": "写作业", "completed": False}]})),
            case("A2", ["R3"], "完成任务并在重启后保持状态", step({"action": "add", "title": "阅读"}, {"ok": True}), step({"action": "complete", "id": 1}, {"ok": True, "task": {"completed": True}}), step({"action": "list"}, {"tasks": [{"id": 1, "title": "阅读", "completed": True}]})),
            case("A3", ["R4"], "删除任务并验证编号不复用", step({"action": "add", "title": "旧任务"}, {"ok": True}), step({"action": "delete", "id": 1}, {"ok": True, "deleted_id": 1}), step({"action": "list"}, {"tasks": []}), step({"action": "add", "title": "新任务"}, {"task": {"id": 2}})),
            case("A4", ["R5"], "拒绝空标题且不产生任务", step({"action": "add", "title": ""}, {"ok": False, "error": "empty_title"}), step({"action": "list"}, {"tasks": []})),
            case("A5", ["R5"], "处理不存在及非法编号", step({"action": "complete", "id": 99}, {"ok": False, "error": "not_found"}), step({"action": "delete", "id": -1}, {"ok": False, "error": "invalid_id"})),
        ],
    }


def benchmark_cases() -> list[dict]:
    """Independent, fixed checks; these are not authored or edited by the agents."""
    cases = [
        case("B1", ["R1", "R2"], "中文标题去除空白；多个任务按顺序保存", step({"action": "add", "title": "  完成课程作业  "}, {"task": {"id": 1, "title": "完成课程作业"}}), step({"action": "add", "title": "复习"}, {"task": {"id": 2}}), step({"action": "list"}, {"ok": True, "tasks": [{"id": 1, "title": "完成课程作业", "completed": False}, {"id": 2, "title": "复习", "completed": False}]})),
        case("B2", ["R5"], "拒绝纯空白与非文本标题", step({"action": "add", "title": " \t "}, {"ok": False, "error": "empty_title"}), step({"action": "add", "title": 123}, {"ok": False, "error": "empty_title"}), step({"action": "list"}, {"tasks": []})),
        case("B3", ["R3", "R5"], "布尔值不能冒充任务编号", step({"action": "add", "title": "保持未完成"}, {"ok": True}), step({"action": "complete", "id": True}, {"ok": False, "error": "invalid_id"}), step({"action": "list"}, {"tasks": [{"id": 1, "completed": False}]})),
        case("B4", ["R4", "R5"], "未知操作与删除不存在的任务", step({"action": "unknown"}, {"ok": False, "error": "unknown_action"}), step({"action": "delete", "id": 999}, {"ok": False, "error": "not_found"}), step({"action": "list"}, {"ok": True, "tasks": []})),
    ]
    for item in cases:
        item["source"] = "benchmark"
    return cases


class DemoClient:
    """Offline fixture responses, including one deliberate defect in the first draft."""

    def complete_json(self, *, agent_name: str, system_prompt: str, user_prompt: str) -> dict:
        del system_prompt
        data = json.loads(user_prompt)
        if agent_name == "requirements":
            if data["user_requirement"].strip() != DEMO_TASK:
                raise LLMError("离线演示仅支持预置待办事项需求；自由需求请使用 DeepSeek 模式。")
            return todo_specification()
        if agent_name == "design":
            return {
                "summary": "入口、业务逻辑与存储分离，使用原子替换保存 JSON 数据。",
                "files": [
                    {"path": "main.py", "purpose": "读取请求，输出 JSON", "requirement_ids": ["R1", "R2", "R3", "R4", "R5"]},
                    {"path": "service.py", "purpose": "任务操作与边界校验", "requirement_ids": ["R1", "R3", "R4", "R5"]},
                    {"path": "storage.py", "purpose": "持久化任务及下一个编号", "requirement_ids": ["R2", "R4"]},
                    {"path": "README.md", "purpose": "协议和运行方法", "requirement_ids": ["R1", "R2", "R3", "R4", "R5"]},
                ],
                "interfaces": [
                    'handle(request: dict) -> dict；操作为 add/list/complete/delete。',
                    'add 使用 title；complete/delete 使用正整数 id，布尔值不作为编号。',
                    '成功返回 ok:true 及 task/tasks/deleted_id；失败返回 ok:false 及 error。',
                    '错误标识：empty_title、invalid_id、not_found、unknown_action、storage_error。',
                ],
                "data_model": 'tasks.json 保存 {"next_id":1,"tasks":[{"id":1,"title":"标题","completed":false}]}。删除后 next_id 不回退。',
            }
        if agent_name == "coding":
            directory = Path(__file__).with_name("fixtures") / "todo_project"
            files = {p.name: p.read_text(encoding="utf-8") for p in directory.iterdir() if p.suffix in {".py", ".md"}}
            repairing = data.get("feedback") is not None
            if not repairing:
                # The harness, not an LLM opinion, discovers this defect.
                files["service.py"] = files["service.py"].replace(
                    '        if not isinstance(title, str) or not title.strip():\n            return {"ok": False, "error": "empty_title"}\n', "",
                )
            return {"summary": "依据执行反馈补充标题类型及空白校验。" if repairing else "已生成三个模块；演示初稿故意遗漏标题校验。", "files": copy.deepcopy(files)}
        raise LLMError(f"未知 Agent：{agent_name}")
