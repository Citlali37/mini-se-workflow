from __future__ import annotations

import json
import re
from pathlib import PurePosixPath
from typing import Any


class ContractError(ValueError):
    """A model response cannot be handed to the next workflow node."""


def text(value: Any, label: str, maximum: int = 6000) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ContractError(f"{label}必须是非空文本，且不超过 {maximum} 字符。")
    return value.strip()


def items(value: Any, label: str, maximum: int = 30, minimum: int = 0) -> list:
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        raise ContractError(f"{label}必须是数组，长度在 {minimum} 到 {maximum} 之间。")
    return value


def object_value(value: Any, label: str) -> dict:
    if not isinstance(value, dict):
        raise ContractError(f"{label}必须是 JSON 对象。")
    return value


def identifier(value: Any, label: str) -> str:
    value = text(value, label, 40)
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", value):
        raise ContractError(f"{label}只能使用英文字母、数字、下划线和连字符。")
    return value


def file_path(value: Any) -> str:
    value = text(value, "文件路径", 100)
    path = PurePosixPath(value)
    # Keep the supported project layout flat and do not permit Windows device names.
    reserved = {"CON", "PRN", "AUX", "NUL"} | {f"{p}{i}" for p in ("COM", "LPT") for i in range(1, 10)}
    if (
        not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*\.(py|md|json|txt)", value)
        or path.stem.upper() in reserved
        or path.stem in {"sitecustomize", "usercustomize"}
        or value.lower() in {"workflow.json", "acceptance.json", "design.json"}
    ):
        raise ContractError("仅支持项目根目录内的普通 .py/.md/.json/.txt 文件名。")
    return value


def references(value: Any, known: set[str], label: str) -> list[str]:
    result = items(value, label, 20, 1)
    if any(not isinstance(item, str) or item not in known for item in result):
        raise ContractError(f"{label}引用了不存在的需求编号。")
    return list(dict.fromkeys(result))


def specification(payload: Any) -> dict:
    payload = object_value(payload, "需求 Agent 输出")
    questions = [text(q, "待确认问题", 1000) for q in items(payload.get("questions", []), "待确认问题", 8)]
    if questions:
        return {"questions": questions, "summary": str(payload.get("summary", "需要补充需求。"))[:6000]}
    requirements = []
    known: set[str] = set()
    for item in items(payload.get("requirements"), "功能需求", 20, 1):
        item = object_value(item, "功能需求")
        key = identifier(item.get("id"), "需求编号")
        if key in known:
            raise ContractError("需求编号不能重复。")
        known.add(key)
        requirements.append({"id": key, "description": text(item.get("description"), "需求说明", 2000)})
    acceptance = []
    seen: set[str] = set()
    covered: set[str] = set()
    for case in items(payload.get("acceptance"), "验收用例", 20, 1):
        case = object_value(case, "验收用例")
        key = identifier(case.get("id"), "验收编号")
        if key in seen:
            raise ContractError("验收编号不能重复。")
        seen.add(key)
        refs = references(case.get("requirement_ids"), known, "验收用例")
        covered.update(refs)
        steps = []
        for step in items(case.get("steps"), "用例步骤", 8, 1):
            step = object_value(step, "用例步骤")
            input_value = object_value(step.get("input"), "用例输入")
            expected = object_value(step.get("expected"), "预期输出")
            if not expected:
                raise ContractError("预期输出不能为空，否则无法验收。")
            if len(json.dumps([input_value, expected], ensure_ascii=False, allow_nan=False)) > 16000:
                raise ContractError("用例输入输出过长。")
            steps.append({"input": input_value, "expected": expected})
        acceptance.append({"id": key, "requirement_ids": refs, "description": text(case.get("description"), "验收说明", 2000), "steps": steps})
    if covered != known:
        raise ContractError("每项需求必须至少被一个验收用例覆盖。")
    return {
        "project_name": text(payload.get("project_name"), "项目名称", 100),
        "summary": text(payload.get("summary"), "需求摘要"),
        "assumptions": [text(a, "假设", 1000) for a in items(payload.get("assumptions", []), "假设", 10)],
        "questions": [], "requirements": requirements, "acceptance": acceptance,
    }


def design(payload: Any, spec: dict) -> dict:
    payload = object_value(payload, "设计 Agent 输出")
    known = {r["id"] for r in spec["requirements"]}
    files = []
    seen: set[str] = set()
    covered: set[str] = set()
    for item in items(payload.get("files"), "设计文件", 10, 1):
        item = object_value(item, "设计文件")
        path = file_path(item.get("path"))
        if path.lower() in seen:
            raise ContractError("设计文件名不能重复（不区分大小写）。")
        seen.add(path.lower())
        refs = references(item.get("requirement_ids"), known, "设计文件")
        covered.update(refs)
        files.append({"path": path, "purpose": text(item.get("purpose"), "文件职责", 2000), "requirement_ids": refs})
    if "main.py" not in {item["path"] for item in files}:
        raise ContractError("设计必须包含统一入口 main.py。")
    if "README.md" not in {item["path"] for item in files}:
        raise ContractError("设计必须包含使用说明 README.md。")
    if covered != known:
        raise ContractError("设计必须覆盖全部需求编号。")
    return {
        "summary": text(payload.get("summary"), "设计摘要"),
        "files": files,
        "interfaces": [text(i, "接口说明", 2000) for i in items(payload.get("interfaces"), "接口说明", 20, 1)],
        "data_model": text(payload.get("data_model"), "数据结构说明"),
    }


def artifact(payload: Any, plan: dict) -> dict:
    payload = object_value(payload, "编码 Agent 输出")
    files = object_value(payload.get("files"), "项目文件")
    planned = {item["path"] for item in plan["files"]}
    if set(files) != planned:
        missing = ", ".join(sorted(planned - set(files))) or "无"
        extra = ", ".join(sorted(set(files) - planned)) or "无"
        raise ContractError(f"编码结果必须完整包含设计中的全部文件，且不能增加未设计的文件。缺少：{missing}；未规划：{extra}。")
    normalized = {}
    for key, value in files.items():
        file_path(key)
        if not isinstance(value, str) or not value.strip() or len(value.encode("utf-8")) > 100000:
            raise ContractError(f"{key}必须是非空文件且不超过 100 KB。")
        normalized[key] = value
    if sum(len(v.encode("utf-8")) for v in normalized.values()) > 300000:
        raise ContractError("项目总大小不能超过 300 KB。")
    return {"summary": text(payload.get("summary"), "编码摘要"), "files": normalized}
