# Mini SE 交付报告

运行编号：e425f15766a347d0
状态：approved
模式：deepseek
已返工：1 / 2

## 原始需求与补充

开发一个待办事项工具：支持新增、查看、完成和删除任务；使用本地 JSON 文件保存，重启后数据不丢失；任务编号从1递增且不复用，标题去除首尾空白，空标题和非文本标题都应拒绝。JSON 请求使用 action 字段：add 携带 title，list 查看列表，complete/delete 携带正整数 id（布尔值不算整数）。新增和完成成功返回 ok:true,task:{id,title,completed}；查看返回 ok:true,tasks 数组（按创建顺序）；删除返回 ok:true,deleted_id。新任务 completed 为 false，完成后为 true。失败返回 ok:false,error：空白或非文本标题为 empty_title，非法编号为 invalid_id，不存在的任务为 not_found，未知操作为 unknown_action。

## 需求确认记录

确认时间：2026-10-13T03:41:56+00:00
规格修改/补充记录：1 条

## 需求追踪

- R1：从 stdin 读取一个 JSON 对象，向 stdout 输出一个 JSON 对象，退出码为 0；业务错误也以 JSON 返回。；文件：main.py, README.md；验收：A1
- R2：数据保存在当前工作目录下 todos.json；每次请求新进程，重启后数据不丢失。；文件：storage.py, README.md；验收：A1, A10
- R3：action=add 且 title 为文本时，去除首尾空白，若结果非空则创建任务，completed=false，返回 ok:true 和 task 对象。；文件：todo.py, README.md；验收：A1, A2, A9
- R4：任务 id 从 1 开始按成功新增顺序递增，删除后不复用；失败新增不占用编号。；文件：todo.py, storage.py, README.md；验收：A8, A11, A13
- R5：action=list 返回 ok:true, tasks 数组，按创建顺序排列，每项含 id、title、completed。；文件：todo.py, README.md；验收：A1, A2, A5, A6, A7, A8, A10, A11, A12, A13
- R6：action=complete 携带正整数 id 时，将对应任务 completed 设为 true，返回 ok:true 和更新后的 task。；文件：todo.py, README.md；验收：A6, A10
- R7：action=delete 携带正整数 id 时，删除对应任务，返回 ok:true, deleted_id。；文件：todo.py, README.md；验收：A7, A10, A12
- R8：title 缺失、非文本或去除首尾空白后为空时，返回 ok:false, error:"empty_title"，不创建任务。；文件：todo.py, README.md；验收：A3, A13
- R9：complete/delete 的 id 缺失、非整数、布尔值或不是正整数时，返回 ok:false, error:"invalid_id"，不修改数据。；文件：todo.py, README.md；验收：A4
- R10：complete/delete 的 id 为正整数但当前无对应任务时，返回 ok:false, error:"not_found"。；文件：todo.py, README.md；验收：A5
- R11：action 缺失、不是已知字符串或未知时，返回 ok:false, error:"unknown_action"。；文件：main.py, README.md；验收：A9
- R12：新任务 completed 为 false；complete 成功后为 true；重复 complete 同一任务仍返回 ok:true 且 completed 为 true。；文件：todo.py, README.md；验收：A1, A6
- R13：删除后任务不再出现在 list 中，其 id 不再分配给新任务。；文件：todo.py, README.md；验收：A7, A8, A12
- R14：请求中额外字段可忽略；成功和失败均输出 JSON 对象，不输出非 JSON 文本。；文件：main.py, README.md；验收：A9
- R15：标题仅去除首尾空白，保留内部空白；全部为空白视为空标题。；文件：todo.py, README.md；验收：A2
- R16：无任务时 list 返回 ok:true 且 tasks 为空数组。；文件：todo.py, README.md；验收：A1, A3, A7

## 每版验收与修改

### 第 1 版

编码输出格式未通过校验。
结果：0/13；未通过
失败原因：编码结果必须完整包含设计中的全部文件，且不能增加未设计的文件。缺少：storage.py, todo.py；未规划：无。

### 第 2 版

实现 todo_tool：main.py 作为 stdin/stdout JSON 协议入口，todo.py 承载业务校验与状态变更，storage.py 负责 todos.json 的容错读取与原子写入，并提供 README.md 使用说明。完整覆盖 add/list/complete/delete 与 empty_title/invalid_id/not_found/unknown_action 四类错误，失败请求不写盘、不占用编号。
结果：13/13；通过
失败原因：无


文件：README.md（added）
```diff
--- before/README.md
+++ after/README.md
@@ -0,0 +1,151 @@
+# todo_tool
+
+一个使用 Python 3.10+ 标准库实现的小型本地待办事项工具。
+每次运行都通过 `python main.py` 启动，从 **stdin** 读取一个 JSON 请求对象，
+向 **stdout** 输出一个 JSON 响应对象，进程退出码固定为 `0`。
+
+数据持久化在当前工作目录下的 `todos.json`，因此每次请求虽然都是新进程，
+数据依然可以跨进程保留。
+
+## 运行方式
+
+```bash
+echo '{"action": "list"}' | python main.py
+```
+
+响应（stdout 只输出一个 JSON 对象）：
+
+```json
+{"ok": true, "tasks": []}
+```
+
+也可以直接交互输入一行 JSON 后按 Ctrl-D（Windows 下 Ctrl-Z 回车）：
+
+```bash
+python main.py
+{"action": "add", "title": "Buy milk"}
+```
+
+## 请求字段
+
+| 字段 | 类型 | 说明 |
+| --- | --- | --- |
+| `action` | 字符串 | 必填，取值 `add` / `list` / `complete` / `delete` |
+| `title` | 字符串 | `add` 使用，去除首尾空白后不能为空 |
+| `id` | JSON 正整数（>= 1） | `complete` / `delete` 使用 |
+
+其他字段一律忽略；布尔值 `true`/`false` 不被视为整数。
+
+## 各 action 的请求与响应
+
+### add
+
+请求：
+
+```json
+{"action": "add", "title": "  Buy milk  "}
+```
+
+成功响应（标题仅去除首尾空白，内部空白保留）：
+
+```json
+{"ok": true, "task": {"id": 1, "title": "Buy milk", "completed": false}}
+```
+
+### list
+
+请求：
+
+```json
+{"action": "list"}
+```
+
+成功响应（按创建顺序排列，无任务时为空数组）：
+
+```json
+{"ok": true, "tasks": [{"id": 1, "title": "Buy milk", "completed": false}]}
+```
+
+### complete
+
+请求：
+
+```json
+{"action": "complete", "id": 1}
+```
+
+成功响应。对已完成任务重复调用是幂等的，仍返回 `ok: true`：
+
+```json
+{"ok": true, "task": {"id": 1, "title": "Buy milk", "completed": true}}
+```
+
+### delete
+
+请求：
+
+```json
+{"action": "delete", "id": 1}
+```
+
+成功响应：
+
+```json
+{"ok": true, "deleted_id": 1}
+```
+
+## 错误行为
+
+所有错误都返回 `{"ok": false, "error": "<标识>"}`，退出码仍为 `0`，
+并且失败请求 **不会修改数据**：
+
+| error | 触发条件 |
+| --- | --- |
+| `unknown_action` | `action` 缺失、不是字符串、未知动作，或输入为空 / 不是合法 JSON 对象 |
+| `empty_title` | `add` 的 `title` 缺失、非字符串或去除首尾空白后为空 |
+| `invalid_id` | `complete` / `delete` 的 `id` 缺失、非整数、布尔值、0 或负数 |
+| `not_found` | `id` 是合法正整数，但当前没有对应任务 |
+
+示例：
+
+```bash
+echo '{"action": "add", "title": "   "}' | python main.py
+# {"ok": false, "error": "empty_title"}
+
+echo '{"action": "complete", "id": true}' | python main.py
+# {"ok": false, "error": "invalid_id"}
+
+echo '{"action": "delete", "id": 99}' | python main.py
+# {"ok": false, "error": "not_found"}
+
+echo '{"action": "nope"}' | python main.py
+# {"ok": false, "error": "unknown_action"}
+```
+
+校验顺序：先校验 `action`，再校验 `title`（add）或 `id`（complete/delete），
+最后校验任务是否存在。
+
+## 编号规则
+
+- 编号从 `1` 开始，只在成功 `add` 时递增。
+- 失败请求不占用编号。
+- 删除后编号不复用。
+
+## 存储格式
+
+当前工作目录下的 `todos.json`：
+
+```json
+{
+  "next_id": 3,
+  "tasks": [
+    {"id": 1, "title": "A", "completed": true},
+    {"id": 3, "title": "C", "completed": false}
+  ]
+}
+```
+
+- 文件不存在、为空或 JSON 解析失败时视为空状态 `{"next_id": 1, "tasks": []}`。
+- 字段缺失或类型异常时做最小兼容：`tasks` 非数组按空数组处理，`next_id` 非正整数按 `1` 处理。
+- 写入使用 UTF-8 编码、`ensure_ascii=False`，先写临时文件再原子替换。
+- 只有发生实际变更的请求才写盘。
```

文件：main.py（added）
```diff
--- before/main.py
+++ after/main.py
@@ -0,0 +1,69 @@
+"""todo_tool 入口模块：stdin 读取一个 JSON 请求，stdout 输出一个 JSON 响应。
+
+退出码固定为 0；业务错误与解析错误均以 JSON 对象返回。
+"""
+
+import json
+import sys
+
+import storage
+import todo
+
+
+def read_request():
+    """从 stdin 读取并解析请求对象；空输入或无法解析时返回 None。"""
+    try:
+        raw = sys.stdin.read()
+    except Exception:
+        return None
+    if not isinstance(raw, str):
+        return None
+    text = raw.strip()
+    if text == "":
+        return None
+    try:
+        return json.loads(text)
+    except Exception:
+        return None
+
+
+def write_response(response):
+    """把响应对象以单个 JSON 文本写入 stdout。"""
+    text = json.dumps(response, ensure_ascii=False)
+    sys.stdout.write(text)
+    sys.stdout.write("\n")
+    try:
+        sys.stdout.flush()
+    except Exception:
+        pass
+
+
+def main():
+    """处理一次请求并返回，进程退出码始终为 0。"""
+    request = read_request()
+    try:
+        state = storage.load_state()
+    except Exception:
+        state = storage.empty_state()
+
+    changed = False
+    if request is None:
+        response = {"ok": False, "error": "unknown_action"}
+    else:
+        try:
+            response, changed = todo.handle_request(request, state)
+        except Exception:
+            response = {"ok": False, "error": "unknown_action"}
+            changed = False
+
+    if changed:
+        try:
+            storage.save_state(state)
+        except Exception:
+            response = {"ok": False, "error": "unknown_action"}
+
+    write_response(response)
+
+
+if __name__ == "__main__":
+    main()
```

文件：storage.py（added）
```diff
--- before/storage.py
+++ after/storage.py
@@ -0,0 +1,88 @@
+"""todo_tool 持久化模块：读写当前工作目录下的 todos.json。
+
+状态结构：{"next_id": int, "tasks": [{"id": int, "title": str, "completed": bool}, ...]}
+"""
+
+import json
+from pathlib import Path
+
+DEFAULT_PATH = "todos.json"
+
+
+def empty_state():
+    """返回空状态。"""
+    return {"next_id": 1, "tasks": []}
+
+
+def _normalize_next_id(value, tasks):
+    """校正 next_id：非正整数按 1 处理，且必须大于所有现存 id。"""
+    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
+        value = 1
+    for task in tasks:
+        if task["id"] >= value:
+            value = task["id"] + 1
+    return value
+
+
+def _normalize_task(item):
+    """把原始条目规范化为任务对象；非法条目返回 None。"""
+    if not isinstance(item, dict):
+        return None
+    task_id = item.get("id")
+    if isinstance(task_id, bool) or not isinstance(task_id, int) or task_id < 1:
+        return None
+    title = item.get("title")
+    if not isinstance(title, str):
+        return None
+    completed = item.get("completed")
+    if not isinstance(completed, bool):
+        completed = False
+    return {"id": task_id, "title": title, "completed": completed}
+
+
+def load_state(path=DEFAULT_PATH):
+    """读取状态；文件不存在、无法读取或解析失败时返回空状态。"""
+    file_path = Path(path)
+    try:
+        text = file_path.read_text(encoding="utf-8")
+    except Exception:
+        return empty_state()
+
+    try:
+        data = json.loads(text)
+    except Exception:
+        return empty_state()
+
+    if not isinstance(data, dict):
+        return empty_state()
+
+    raw_tasks = data.get("tasks")
+    tasks = []
+    if isinstance(raw_tasks, list):
+        for item in raw_tasks:
+            task = _normalize_task(item)
+            if task is not None:
+                tasks.append(task)
+
+    return {"next_id": _normalize_next_id(data.get("next_id"), tasks), "tasks": tasks}
+
+
+def save_state(state, path=DEFAULT_PATH):
+    """以 UTF-8 原子写入状态：先写同目录临时文件再替换目标文件。"""
+    file_path = Path(path)
+    tasks = state.get("tasks")
+    if not isinstance(tasks, list):
+        tasks = []
+    next_id = state.get("next_id")
+    if isinstance(next_id, bool) or not isinstance(next_id, int) or next_id < 1:
+        next_id = 1
+
+    payload = {
+        "next_id": next_id,
+        "tasks": [_normalize_task(t) for t in tasks if _normalize_task(t) is not None],
+    }
+    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
+
+    tmp_path = file_path.with_name(file_path.name + ".tmp")
+    tmp_path.write_text(text, encoding="utf-8")
+    tmp_path.replace(file_path)
```

文件：todo.py（added）
```diff
--- before/todo.py
+++ after/todo.py
@@ -0,0 +1,94 @@
+"""todo_tool 业务逻辑：校验请求并修改内存状态。
+
+handle_request(request, state) -> (response, changed)
+changed 为 True 时表示状态被修改，需要写盘。
+"""
+
+import storage
+
+KNOWN_ACTIONS = ("add", "list", "complete", "delete")
+
+
+def _is_positive_int(value):
+    """判断是否为 JSON 正整数（布尔值不算整数）。"""
+    if isinstance(value, bool):
+        return False
+    if not isinstance(value, int):
+        return False
+    return value >= 1
+
+
+def _clean_title(value):
+    """校验并清洗标题；非法或空白返回 None。"""
+    if not isinstance(value, str):
+        return None
+    stripped = value.strip()
+    if stripped == "":
+        return None
+    return stripped
+
+
+def _find_task(tasks, task_id):
+    """按 id 查找任务，找不到返回 None。"""
+    for task in tasks:
+        if task["id"] == task_id:
+            return task
+    return None
+
+
+def _public_task(task):
+    """构造对外输出的任务对象。"""
+    return {
+        "id": task["id"],
+        "title": task["title"],
+        "completed": task["completed"],
+    }
+
+
+def _error(name):
+    return {"ok": False, "error": name}
+
+
+def handle_request(request, state):
+    """处理单个请求，返回 (response, changed)。"""
+    if not isinstance(request, dict):
+        return _error("unknown_action"), False
+
+    action = request.get("action")
+    if not isinstance(action, str) or action not in KNOWN_ACTIONS:
+        return _error("unknown_action"), False
+
+    tasks = state.get("tasks")
+    if not isinstance(tasks, list):
+        tasks = []
+        state["tasks"] = tasks
+
+    if action == "add":
+        title = _clean_title(request.get("title"))
+        if title is None:
+            return _error("empty_title"), False
+        next_id = state.get("next_id")
+        if not _is_positive_int(next_id):
+            next_id = 1
+        task = {"id": next_id, "title": title, "completed": False}
+        tasks.append(task)
+        state["next_id"] = next_id + 1
+        return {"ok": True, "task": _public_task(task)}, True
+
+    if action == "list":
+        return {"ok": True, "tasks": [_public_task(t) for t in tasks]}, False
+
+    task_id = request.get("id")
+    if not _is_positive_int(task_id):
+        return _error("invalid_id"), False
+
+    task = _find_task(tasks, task_id)
+    if task is None:
+        return _error("not_found"), False
+
+    if action == "complete":
+        task["completed"] = True
+        return {"ok": True, "task": _public_task(task)}, True
+
+    tasks.remove(task)
+    return {"ok": True, "deleted_id": task_id}, True
```

## 独立评测

评测编号：todo；模式：deepseek
评测结果：通过；与流程验收状态分别记录。
套件 SHA256：f22a78767b4489175e090ba2259c9a8bfce40f25e16effcffb910798b4a8f086
独立用例：4/4
- B1 中文标题去除空白；多个任务按顺序保存：通过
- B2 拒绝纯空白与非文本标题：通过
- B3 布尔值不能冒充任务编号：通过
- B4 未知操作与删除不存在的任务：通过

## 已记录阶段耗时

- 需求 Agent：35458 ms
- 设计 Agent：11295 ms
- 验收执行器：2 ms
- 编码 Agent：18725 ms
- Workflow：4671 ms

## 限制与解释

通过只表示满足当前验收集，不保证所有输入正确。独立评测结果应另行查看。
模型生成的需求及用例可能遗漏用户意图；需求编号关联用于追踪，不能证明语义正确。
执行使用本机 Python，范围检查不是操作系统级沙箱。
取消与恢复以节点/检查点为单位；不能恢复某个模型请求内部的执行。
未恢复异常：无
