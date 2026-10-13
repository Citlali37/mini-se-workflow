# Mini SE 交付报告

运行编号：831ac841b9024055
状态：approved
模式：deepseek
已返工：0 / 2

## 原始需求与补充

开发本地支出记账工具，数据JSON持久保存。请求action:add包含正整数amount（以分计，布尔值非法）及非空字符串category（去除首尾空白），返回ok:true,entry:{amount,category}；action:list返回ok:true,entries数组（创建顺序）；action:total返回ok:true,total（总金额整数，初始0）。非法金额返回ok:false,error:"invalid_amount"，非法分类返回ok:false,error:"invalid_category"，未知操作返回ok:false,error:"unknown_action"。每请求重启进程。

## 需求确认记录

确认时间：2026-10-13T03:43:45+00:00
规格修改/补充记录：1 条

## 需求追踪

- R1：从 stdin 读取一个 JSON 对象，执行一次请求，stdout 只输出一个 JSON 对象且退出码为 0。；文件：main.py, protocol.py, README.md；验收：A1
- R2：数据持久化到当前工作目录 expenses.json；文件不存在时视为空数据。；文件：storage.py, README.md；验收：A1, A9
- R3：add 仅接受正整数 amount（以分计），布尔值非法；否则返回 ok:false,error:"invalid_amount"。；文件：validation.py, handlers.py, README.md；验收：A5, A6, A10
- R4：add 仅接受字符串 category，去除首尾空白后必须非空；否则返回 ok:false,error:"invalid_category"。；文件：validation.py, handlers.py, README.md；验收：A2, A7, A11
- R5：add 成功时追加条目并返回 ok:true,entry:{amount,category}，category 为去除首尾空白后的值。；文件：handlers.py, README.md；验收：A1, A2, A3, A11
- R6：list 返回 ok:true,entries 数组，按创建顺序，每项包含 amount 和 category。；文件：handlers.py, README.md；验收：A1, A2, A3, A4
- R7：total 返回 ok:true,total，为所有条目 amount 的整数总和，空数据为 0。；文件：handlers.py, README.md；验收：A1, A3, A4, A10
- R8：未知 action（缺失、非字符串、未识别）返回 ok:false,error:"unknown_action"。；文件：main.py, protocol.py, handlers.py, README.md；验收：A8
- R9：非法请求不改变持久化条目；错误响应包含 ok:false 与对应 error。；文件：storage.py, handlers.py, README.md；验收：A5, A6, A7, A8, A9
- R10：每次请求新进程，状态仅通过持久化文件在请求间保留。；文件：main.py, storage.py, README.md；验收：A1, A9

## 每版验收与修改

### 第 1 版

实现本地支出记账工具：main.py 入口、protocol.py JSON 协议层、validation.py 校验、storage.py expenses.json 持久化、handlers.py 业务分发（add/list/total 与错误分支），全部错误以 ok:false JSON 返回且退出码 0。
结果：11/11；通过
失败原因：无


文件：README.md（added）
```diff
--- before/README.md
+++ after/README.md
@@ -0,0 +1,109 @@
+# 本地支出记账工具
+
+一个仅使用 Python 3.10+ 标准库的小型本地工具：从 stdin 读取一个 JSON 请求，
+执行一次操作，向 stdout 输出一个 JSON 响应，退出码恒为 0。
+所有数据保存在**当前工作目录**下的 `expenses.json`，因此可以跨进程保留状态。
+
+## 使用方法
+
+```bash
+echo '{"action": "add", "amount": 500, "category": "Food"}' | python main.py
+```
+
+每次调用都是一个新进程；进程之间唯一的共享状态就是当前工作目录下的 `expenses.json`。
+
+## 请求协议
+
+- 从 stdin 读取的内容必须是一个 JSON 对象；空输入、非法 JSON 或顶层不是对象时，
+  等价于缺少 `action`，返回 `unknown_action`。
+- 只执行一次请求，stdout 只输出一个 JSON 对象，没有其他文本，退出码为 0。
+
+### action: add
+
+```json
+{"action": "add", "amount": 500, "category": "Food"}
+```
+
+- `amount`：必须是 JSON 整数且大于 0（以分计）。布尔值、浮点数、字符串、null、0 和负数都非法。
+- `category`：必须是字符串，去除首尾空白后不能为空；内部空白保留。
+- 成功响应（`category` 为去除首尾空白后的值）：
+
+```json
+{"ok": true, "entry": {"amount": 500, "category": "Food"}}
+```
+
+### action: list
+
+```json
+{"action": "list"}
+```
+
+返回按创建顺序排列的全部条目：
+
+```json
+{"ok": true, "entries": [{"amount": 500, "category": "Food"}]}
+```
+
+没有数据时 `entries` 为空数组 `[]`。
+
+### action: total
+
+```json
+{"action": "total"}
+```
+
+返回所有条目 `amount` 的整数总和：
+
+```json
+{"ok": true, "total": 500}
+```
+
+没有数据时 `total` 为 `0`。
+
+## 错误行为
+
+所有错误都以 `ok:false` 的 JSON 返回，退出码仍然为 0，且**不修改**持久化数据：
+
+| 情况 | 响应 |
+| --- | --- |
+| `amount` 缺失 / 非整数 / 布尔值 / 小于等于 0 | `{"ok": false, "error": "invalid_amount"}` |
+| `category` 缺失 / 非字符串 / 去空白后为空 | `{"ok": false, "error": "invalid_category"}` |
+| `action` 缺失 / 非字符串 / 未识别 | `{"ok": false, "error": "unknown_action"}` |
+
+`add` 的校验顺序为先 `amount` 后 `category`。
+
+示例：
+
+```bash
+echo '{"action": "add", "amount": 0, "category": "X"}' | python main.py
+# {"ok": false, "error": "invalid_amount"}
+
+echo '{"action": "add", "amount": 100, "category": "   "}' | python main.py
+# {"ok": false, "error": "invalid_category"}
+
+echo '{"action": "delete"}' | python main.py
+# {"ok": false, "error": "unknown_action"}
+
+echo '{}' | python main.py
+# {"ok": false, "error": "unknown_action"}
+```
+
+## 持久化格式
+
+文件路径：`expenses.json`（当前工作目录，UTF-8 文本）。
+
+```json
+{"entries": [{"amount": 500, "category": "Food"}, {"amount": 250, "category": "B"}]}
+```
+
+- 数组顺序即创建顺序，成功的 `add` 追加到末尾。
+- 文件不存在、读取失败、JSON 非法或顶层结构不合法时，视为空数据 `[]`（不报错）。
+- 只有成功的 `add` 才会覆盖写入该文件；失败的请求绝不写盘。
+
+## 文件结构
+
+- `main.py`：进程入口，负责 stdin 读取、分发调用、stdout 输出与兜底异常处理。
+- `protocol.py`：请求解析与响应写出。
+- `validation.py`：`amount` / `category` 校验。
+- `storage.py`：`expenses.json` 读写与容错。
+- `handlers.py`：`add` / `list` / `total` 业务与错误分支。
```

文件：handlers.py（added）
```diff
--- before/handlers.py
+++ after/handlers.py
@@ -0,0 +1,59 @@
+"""业务层：请求分发与 add/list/total 处理。
+
+失败路径一律不写盘，保证非法请求零副作用。
+"""
+
+import storage
+import validation
+
+ADD = "add"
+LIST = "list"
+TOTAL = "total"
+
+
+def dispatch(request: dict) -> dict:
+    """根据 action 分发请求；未知或缺失 action 返回 unknown_action。"""
+    if not isinstance(request, dict):
+        return {"ok": False, "error": "unknown_action"}
+    action = request.get("action")
+    if not isinstance(action, str):
+        return {"ok": False, "error": "unknown_action"}
+    if action == ADD:
+        return handle_add(request)
+    if action == LIST:
+        return handle_list(request)
+    if action == TOTAL:
+        return handle_total(request)
+    return {"ok": False, "error": "unknown_action"}
+
+
+def handle_add(request: dict) -> dict:
+    """校验并追加一条支出记录，成功时持久化。"""
+    amount = request.get("amount")
+    if not validation.validate_amount(amount):
+        return {"ok": False, "error": "invalid_amount"}
+
+    cleaned = validation.validate_category(request.get("category"))
+    if cleaned is None:
+        return {"ok": False, "error": "invalid_category"}
+
+    entries = storage.load_entries()
+    entry = {"amount": amount, "category": cleaned}
+    entries.append(entry)
+    storage.save_entries(entries)
+    return {"ok": True, "entry": {"amount": amount, "category": cleaned}}
+
+
+def handle_list(request: dict) -> dict:
+    """按创建顺序返回全部条目。"""
+    entries = storage.load_entries()
+    return {"ok": True, "entries": entries}
+
+
+def handle_total(request: dict) -> dict:
+    """返回所有条目 amount 的整数总和，空数据为 0。"""
+    entries = storage.load_entries()
+    total = 0
+    for entry in entries:
+        total += entry["amount"]
+    return {"ok": True, "total": total}
```

文件：main.py（added）
```diff
--- before/main.py
+++ after/main.py
@@ -0,0 +1,44 @@
+"""本地支出记账工具入口。
+
+从 stdin 读取一个 JSON 对象，执行一次请求，向 stdout 写出一个 JSON 对象，
+退出码恒为 0。所有状态通过当前工作目录下的 expenses.json 跨进程保留。
+"""
+
+import sys
+
+import handlers
+import protocol
+
+
+def configure_stdio() -> None:
+    """尽量把标准流切换为 UTF-8，避免本地化编码影响 JSON 的读写。"""
+    streams = (sys.stdin, sys.stdout)
+    for stream in streams:
+        try:
+            stream.reconfigure(encoding="utf-8")
+        except Exception:
+            continue
+
+
+def main() -> int:
+    configure_stdio()
+    try:
+        data = sys.stdin.read()
+    except Exception:
+        data = ""
+
+    try:
+        request = protocol.read_request(data)
+        response = handlers.dispatch(request)
+    except Exception:
+        response = {"ok": False, "error": "unknown_action"}
+
+    try:
+        protocol.write_response(response)
+    except Exception:
+        return 0
+    return 0
+
+
+if __name__ == "__main__":
+    sys.exit(main())
```

文件：protocol.py（added）
```diff
--- before/protocol.py
+++ after/protocol.py
@@ -0,0 +1,34 @@
+"""JSON 协议层：stdin 请求解析与 stdout 响应写出。
+
+任何无法解析为 JSON 对象的输入都退化为空字典 {}，从而由业务层统一
+判定为 unknown_action。写出时只输出一个 JSON 对象，不追加额外文本。
+"""
+
+import json
+import sys
+
+
+def read_request(data: str) -> dict:
+    """把 stdin 文本解析为请求对象。
+
+    空输入、非字符串、非法 JSON、或解析结果不是对象时返回 {}。
+    """
+    if not isinstance(data, str):
+        return {}
+    text = data.strip()
+    if text == "":
+        return {}
+    try:
+        parsed = json.loads(text)
+    except Exception:
+        return {}
+    if isinstance(parsed, dict):
+        return parsed
+    return {}
+
+
+def write_response(resp: dict) -> None:
+    """把响应对象写成单个 JSON 对象并刷新缓冲区。"""
+    payload = json.dumps(resp, ensure_ascii=False)
+    sys.stdout.write(payload)
+    sys.stdout.flush()
```

文件：storage.py（added）
```diff
--- before/storage.py
+++ after/storage.py
@@ -0,0 +1,69 @@
+"""持久化层：当前工作目录下 expenses.json 的读写与容错。
+
+文件格式为单个 JSON 对象 {"entries": [{"amount": int, "category": str}, ...]}，
+数组顺序即创建顺序。文件缺失或内容不可用时按空数据处理。
+"""
+
+import json
+from pathlib import Path
+
+STORAGE_PATH = "expenses.json"
+
+
+def _storage_file() -> Path:
+    return Path(STORAGE_PATH)
+
+
+def _normalize_entry(item) -> dict:
+    """把持久化中的一条记录规范为仅含 amount 与 category 的字典。"""
+    if not isinstance(item, dict):
+        return {}
+    amount = item.get("amount")
+    category = item.get("category")
+    if isinstance(amount, bool):
+        return {}
+    if not isinstance(amount, int):
+        return {}
+    if not isinstance(category, str):
+        return {}
+    return {"amount": amount, "category": category}
+
+
+def load_entries() -> list:
+    """读取全部条目；文件不存在、读取失败或结构非法时返回空列表。"""
+    path = _storage_file()
+    try:
+        text = path.read_text(encoding="utf-8")
+    except OSError:
+        return []
+    except Exception:
+        return []
+
+    if text.strip() == "":
+        return []
+
+    try:
+        data = json.loads(text)
+    except Exception:
+        return []
+
+    if not isinstance(data, dict):
+        return []
+
+    raw_entries = data.get("entries")
+    if not isinstance(raw_entries, list):
+        return []
+
+    entries = []
+    for item in raw_entries:
+        entry = _normalize_entry(item)
+        if entry:
+            entries.append(entry)
+    return entries
+
+
+def save_entries(entries: list) -> None:
+    """整体覆盖写入 entries 列表。"""
+    path = _storage_file()
+    payload = json.dumps({"entries": entries}, ensure_ascii=False)
+    path.write_text(payload, encoding="utf-8")
```

文件：validation.py（added）
```diff
--- before/validation.py
+++ after/validation.py
@@ -0,0 +1,22 @@
+"""输入校验：amount 与 category 的合法性判定。"""
+
+
+def validate_amount(amount) -> bool:
+    """amount 必须是 JSON 整数且严格大于 0；布尔值不被视为整数。"""
+    if isinstance(amount, bool):
+        return False
+    if not isinstance(amount, int):
+        return False
+    if amount <= 0:
+        return False
+    return True
+
+
+def validate_category(category):
+    """category 必须是字符串，去除首尾空白后非空；返回清洗后的值，否则 None。"""
+    if not isinstance(category, str):
+        return None
+    cleaned = category.strip()
+    if cleaned == "":
+        return None
+    return cleaned
```

## 独立评测

评测编号：ledger；模式：deepseek
评测结果：通过；与流程验收状态分别记录。
套件 SHA256：f22a78767b4489175e090ba2259c9a8bfce40f25e16effcffb910798b4a8f086
独立用例：2/2
- L1 持久化和总金额：通过
- L2 非法请求不改变数据：通过

## 已记录阶段耗时

- 需求 Agent：21669 ms
- 设计 Agent：14812 ms
- 编码 Agent：17131 ms
- Workflow：2903 ms

## 限制与解释

通过只表示满足当前验收集，不保证所有输入正确。独立评测结果应另行查看。
模型生成的需求及用例可能遗漏用户意图；需求编号关联用于追踪，不能证明语义正确。
执行使用本机 Python，范围检查不是操作系统级沙箱。
取消与恢复以节点/检查点为单位；不能恢复某个模型请求内部的执行。
未恢复异常：无
