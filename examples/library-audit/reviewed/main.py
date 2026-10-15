"""本地图书借阅工具入口：从 stdin 读取单个 JSON 请求并输出单个 JSON 响应。"""

import json
import sys

from handlers import MUTATING_ACTIONS, handle
from storage import StorageError, load_library, save_library


def emit(response):
    """把响应对象以 UTF-8 JSON 单行写入 stdout。"""
    text = json.dumps(response, ensure_ascii=False)
    sys.stdout.write(text + "\n")
    sys.stdout.flush()


def parse_request(raw):
    """解析 stdin 文本；空输入或非 JSON 对象返回 None。"""
    if not isinstance(raw, str):
        return None
    if raw.strip() == "":
        return None
    try:
        parsed = json.loads(raw, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    except ValueError:
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed


def main():
    raw = sys.stdin.read()
    request = parse_request(raw)
    if request is None:
        emit({"ok": False, "error": "invalid_request"})
        return 0

    try:
        data = load_library()
        action = request.get("action")
        response = handle(request, data)
        if response.get("ok") is True and isinstance(action, str) and action in MUTATING_ACTIONS:
            save_library(data)
    except StorageError:
        response = {"ok": False, "error": "storage_error"}

    emit(response)
    return 0


if __name__ == "__main__":
    sys.exit(main())
