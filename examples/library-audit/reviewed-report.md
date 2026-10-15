# Mini SE 交付报告

运行编号：ff240698112c46e4
状态：approved
模式：human_reviewed
已返工：1 / 1

## 原始需求与补充

开发一个本地图书借阅管理工具，支持添加图书、登记读者、借书、还书和查询借阅记录。

每本图书有唯一编号、书名和总库存，每位读者有唯一编号和姓名。借书时记录借阅日期及应还日期，可借库存减一；还书后库存恢复。库存不足不能借出，同一读者不能重复借阅同一本尚未归还的图书，已经归还的记录不能重复归还。

支持按读者查询未归还图书，并根据用户提供的查询日期列出逾期记录。借阅期限固定为14天，应还日期当天不算逾期。

数据保存到本地JSON文件，程序重启后仍然保留。非法编号、错误日期和不存在的图书或读者应返回明确错误，失败操作不能改变已有数据。使用Python标准库，不需要联网或图形界面。

质量补充：必填字段严格校验；存储异常保留原数据并报错。

## 需求确认记录

确认时间：2026-10-15T06:21:20+00:00
规格修改/补充记录：2 条

## 需求追踪

- R1：add_book：添加图书，需提供 book_id、title、total_copies；book_id 全局唯一，重复时返回 duplicate_book_id；成功返回 {"ok":true,"book":{"book_id":..,"title":..,"total_copies":..}}。 title必须为非空白字符串，去除首尾空白；否则invalid_title。；文件：main.py, handlers.py, README.md；验收：A1, A8, A9
- R2：add_reader：登记读者，需提供 reader_id、name；reader_id 唯一，重复时返回 duplicate_reader_id；成功返回 {"ok":true,"reader":{"reader_id":..,"name":..}}。 name必须为非空白字符串，去除首尾空白；否则invalid_name。；文件：main.py, handlers.py, README.md；验收：A1, A9
- R3：borrow：借书，需提供 book_id、reader_id、borrow_date；成功时记录借阅日期和应还日期（due_date = borrow_date + 14 天），返回 {"ok":true,"available_copies":N,"record":{"book_id":..,"reader_id":..,"borrow_date":..,"due_date":..,"returned":false}}，可借库存减一。；文件：main.py, handlers.py, validators.py, README.md；验收：A1, A3, A7
- R4：return_book：还书，需提供 book_id、reader_id、return_date；将该读者对该图书的未归还记录标记为已归还并记录 return_date，返回 {"ok":true,"available_copies":N,"record":{"book_id":..,"reader_id":..,"return_date":..,"returned":true}}，可借库存加一。；文件：main.py, handlers.py, README.md；验收：A2, A3, A8
- R5：库存不足：当某图书的未归还借阅数等于 total_copies 时，借书返回 {"ok":false,"error":"no_copies_available"}，且不产生任何数据变更。；文件：main.py, handlers.py, README.md；验收：A2
- R6：同一读者对同一本图书已有未归还借阅时，再次借阅返回 {"ok":false,"error":"already_borrowed"}。；文件：main.py, handlers.py, README.md；验收：A5
- R7：对不存在未归还借阅的图书/读者组合执行还书（含重复归还已归还记录）返回 {"ok":false,"error":"not_borrowed"}。；文件：main.py, handlers.py, README.md；验收：A3
- R8：list_borrowed：按 reader_id 查询该读者所有未归还借阅，返回 {"ok":true,"borrows":[{"book_id":..,"title":..,"borrow_date":..,"due_date":..}]}，按借阅登记顺序升序；reader_id 不存在返回 reader_not_found。；文件：main.py, handlers.py, README.md；验收：A3, A7
- R9：list_overdue：提供必填 date 与可选 reader_id，返回 due_date < date 的未归还记录 {"ok":true,"overdue":[{"reader_id":..,"book_id":..,"title":..,"borrow_date":..,"due_date":..}]}，按借阅登记顺序升序。；文件：main.py, handlers.py, README.md；验收：A4
- R10：持久化：所有图书、读者与借阅记录保存在当前工作目录下的 library_data.json，每次请求重启进程后数据仍可用；文件不存在时按空库处理。 损坏、结构非法、读取或写入失败时返回storage_error并保留旧文件；使用同目录临时文件替换保存。；文件：main.py, storage.py, README.md；验收：A8
- R11：错误处理：book_id/reader_id 非非空字符串返回 invalid_id；日期非法或格式不是 YYYY-MM-DD 返回 invalid_date；图书不存在返回 book_not_found；读者不存在返回 reader_not_found；total_copies 不是 ≥1 的整数返回 invalid_total_copies；未识别 action 返回 unknown_action；所有失败请求不修改已保存数据。 拒绝纯空白编号；日期加14天溢出返回invalid_date。；文件：main.py, handlers.py, validators.py, README.md；验收：A2, A6, A9

## 每版验收与修改

### 第 1 版

原始模型产物按新增规格复验
结果：8/9；未通过
失败原因：A9

- A9：$.ok 预期 False，实际 True。

文件：README.md（added）
```diff
--- before/README.md
+++ after/README.md
@@ -0,0 +1,125 @@
+# local-library-lending
+
+一个零依赖（Python 3.10+ 标准库）的本地图书借阅管理工具。每次调用都是一个独立进程：
+从 stdin 读取一个 JSON 请求，执行一次操作，向 stdout 输出一个 JSON 响应，退出码始终为 0。
+数据持久化在当前工作目录下的相对路径 `library_data.json`。
+
+## 使用方法
+
+```bash
+python main.py
+```
+
+然后从标准输入传入一个 JSON 对象（通常通过管道或重定向）。输出是单行 UTF-8 JSON。
+
+```bash
+# Linux / macOS
+echo '{"action":"add_book","book_id":"B1","title":"算法导论","total_copies":2}' | python main.py
+
+# Windows PowerShell
+'{"action":"add_book","book_id":"B1","title":"算法导论","total_copies":2}' | python main.py
+```
+
+## 响应信封
+
+* 成功：`{"ok": true, ...}`
+* 失败：`{"ok": false, "error": "<错误码>"}`
+
+stdin 为空、不是合法 JSON 或不是 JSON 对象时返回 `{"ok": false, "error": "invalid_request"}`。
+
+## 动作与请求示例
+
+### add_book
+
+请求：`{"action":"add_book","book_id":"B1","title":"算法导论","total_copies":2}`
+
+成功：`{"ok":true,"book":{"book_id":"B1","title":"算法导论","total_copies":2}}`
+
+错误：`invalid_id`、`invalid_total_copies`、`duplicate_book_id`。
+
+### add_reader
+
+请求：`{"action":"add_reader","reader_id":"R1","name":"张三"}`
+
+成功：`{"ok":true,"reader":{"reader_id":"R1","name":"张三"}}`
+
+错误：`invalid_id`、`duplicate_reader_id`。
+
+### borrow
+
+请求：`{"action":"borrow","book_id":"B1","reader_id":"R1","borrow_date":"2024-03-01"}`
+
+成功：`{"ok":true,"available_copies":1,"record":{"book_id":"B1","reader_id":"R1","borrow_date":"2024-03-01","due_date":"2024-03-15","returned":false}}`
+
+错误：`invalid_id`、`invalid_date`、`book_not_found`、`reader_not_found`、`already_borrowed`、`no_copies_available`。
+
+### return_book
+
+请求：`{"action":"return_book","book_id":"B1","reader_id":"R1","return_date":"2024-03-05"}`
+
+成功：`{"ok":true,"available_copies":2,"record":{"book_id":"B1","reader_id":"R1","return_date":"2024-03-05","returned":true}}`
+
+错误：`invalid_id`、`invalid_date`、`book_not_found`、`reader_not_found`、`not_borrowed`（含重复归还）。
+
+### list_borrowed
+
+请求：`{"action":"list_borrowed","reader_id":"R1"}`
+
+成功：`{"ok":true,"borrows":[{"book_id":"B1","title":"算法导论","borrow_date":"2024-03-01","due_date":"2024-03-15"}]}`
+
+只返回未归还（`returned=false`）的记录，按借阅登记顺序（seq）升序。错误：`invalid_id`、`reader_not_found`。
+
+### list_overdue
+
+请求：`{"action":"list_overdue","date":"2024-03-16"}` 或 `{"action":"list_overdue","date":"2024-03-16","reader_id":"R1"}`
+
+成功：`{"ok":true,"overdue":[{"reader_id":"R1","book_id":"B1","title":"算法导论","borrow_date":"2024-03-01","due_date":"2024-03-15"}]}`
+
+判定条件：未归还且 `due_date < date`（应还日期当天不算逾期）。不传 `reader_id` 时返回全部读者，按借阅登记顺序升序。
+错误：`invalid_date`、`invalid_id`、`reader_not_found`。
+
+### 其他
+
+无法识别、缺失或非字符串的 `action` 返回 `{"ok":false,"error":"unknown_action"}`。
+
+## 业务规则
+
+* `book_id` / `reader_id` 必须是非空字符串，否则 `invalid_id`。
+* `total_copies` 必须是 ≥ 1 的整数（布尔值不算），否则 `invalid_total_copies`。
+* 日期必须严格为 `YYYY-MM-DD` 且是真实存在的公历日期（`2024-02-30`、`2024/01/01` 均非法），否则 `invalid_date`。
+* 借阅期限固定 14 天：`due_date = borrow_date + 14 天`。
+* 可借库存 `available_copies = total_copies − 该图书未归还的借阅记录数`；归还后库存恢复。
+* 同一读者对同一本图书已有未归还借阅时，再次借阅返回 `already_borrowed`（优先于 `no_copies_available`）。
+* 库存不足（未归还数等于 `total_copies`）时返回 `no_copies_available`，且不产生任何数据变更。
+* `return_date` 只校验为合法日期，不要求晚于 `borrow_date`。
+* 错误判定优先级：`invalid_id` → `invalid_date` → `book_not_found` → `reader_not_found` → 业务冲突（`duplicate_book_id`/`duplicate_reader_id`/`already_borrowed`/`no_copies_available`/`not_borrowed`）。
+* 任何失败请求都不会修改已保存的数据，只有成功的写操作（add_book / add_reader / borrow / return_book）才写回文件。
+
+## 存储格式
+
+数据保存在当前工作目录下的 `library_data.json`（UTF-8）。文件不存在、不可读或 JSON 解析失败时按空库处理。
+
+```json
+{
+  "next_seq": 2,
+  "books": {
+    "B1": {"book_id": "B1", "title": "算法导论", "total_copies": 2}
+  },
+  "readers": {
+    "R1": {"reader_id": "R1", "name": "张三"}
+  },
+  "borrows": [
+    {
+      "seq": 1,
+      "book_id": "B1",
+      "reader_id": "R1",
+      "borrow_date": "2024-03-01",
+      "due_date": "2024-03-15",
+      "returned": false,
+      "return_date": null
+    }
+  ]
+}
+```
+
+已归还的记录保留在 `borrows` 中（`returned=true` 且有 `return_date`），但不再占用库存，也不会出现在未归还列表或逾期列表中。
```

文件：handlers.py（added）
```diff
--- before/handlers.py
+++ after/handlers.py
@@ -0,0 +1,269 @@
+"""图书借阅工具的业务逻辑：动作分发、校验顺序、库存与逾期计算。"""
+
+from validators import add_days, format_date, is_valid_id, is_valid_total_copies, parse_date
+
+MUTATING_ACTIONS = {"add_book", "add_reader", "borrow", "return_book"}
+LOAN_DAYS = 14
+
+
+def error(code):
+    return {"ok": False, "error": code}
+
+
+def as_text(value):
+    """title/name 缺失或非字符串时按空字符串处理。"""
+    if isinstance(value, str):
+        return value
+    return ""
+
+
+def active_count(borrows, book_id):
+    """该图书当前未归还的借阅数量。"""
+    total = 0
+    for record in borrows:
+        if record.get("book_id") == book_id and not record.get("returned"):
+            total += 1
+    return total
+
+
+def find_active_borrow(borrows, book_id, reader_id):
+    """查找该 (book_id, reader_id) 最早的未归还记录，没有则返回 None。"""
+    for record in borrows:
+        if record.get("book_id") != book_id:
+            continue
+        if record.get("reader_id") != reader_id:
+            continue
+        if record.get("returned"):
+            continue
+        return record
+    return None
+
+
+def book_title(books, book_id):
+    book = books.get(book_id)
+    if isinstance(book, dict):
+        title = book.get("title")
+        if isinstance(title, str):
+            return title
+    return ""
+
+
+def handle_add_book(request, data):
+    book_id = request.get("book_id")
+    if not is_valid_id(book_id):
+        return error("invalid_id")
+    total_copies = request.get("total_copies")
+    if not is_valid_total_copies(total_copies):
+        return error("invalid_total_copies")
+
+    books = data["books"]
+    if book_id in books:
+        return error("duplicate_book_id")
+
+    book = {
+        "book_id": book_id,
+        "title": as_text(request.get("title")),
+        "total_copies": total_copies,
+    }
+    books[book_id] = book
+    return {
+        "ok": True,
+        "book": {
+            "book_id": book["book_id"],
+            "title": book["title"],
+            "total_copies": book["total_copies"],
+        },
+    }
+
+
+def handle_add_reader(request, data):
+    reader_id = request.get("reader_id")
+    if not is_valid_id(reader_id):
+        return error("invalid_id")
+
+    readers = data["readers"]
+    if reader_id in readers:
+        return error("duplicate_reader_id")
+
+    reader = {"reader_id": reader_id, "name": as_text(request.get("name"))}
+    readers[reader_id] = reader
+    return {
+        "ok": True,
+        "reader": {"reader_id": reader["reader_id"], "name": reader["name"]},
+    }
+
+
+def handle_borrow(request, data):
+    book_id = request.get("book_id")
+    reader_id = request.get("reader_id")
+    if not is_valid_id(book_id) or not is_valid_id(reader_id):
+        return error("invalid_id")
+
+    borrow_date = parse_date(request.get("borrow_date"))
+    if borrow_date is None:
+        return error("invalid_date")
+
+    books = data["books"]
+    readers = data["readers"]
+    if book_id not in books:
+        return error("book_not_found")
+    if reader_id not in readers:
+        return error("reader_not_found")
+
+    borrows = data["borrows"]
+    if find_active_borrow(borrows, book_id, reader_id) is not None:
+        return error("already_borrowed")
+
+    book = books[book_id]
+    if active_count(borrows, book_id) >= book["total_copies"]:
+        return error("no_copies_available")
+
+    due_date = add_days(borrow_date, LOAN_DAYS)
+    seq = data.get("next_seq")
+    if not isinstance(seq, int) or isinstance(seq, bool) or seq < 1:
+        seq = 1
+    record = {
+        "seq": seq,
+        "book_id": book_id,
+        "reader_id": reader_id,
+        "borrow_date": format_date(borrow_date),
+        "due_date": format_date(due_date),
+        "returned": False,
+        "return_date": None,
+    }
+    borrows.append(record)
+    data["next_seq"] = seq + 1
+
+    available = book["total_copies"] - active_count(borrows, book_id)
+    return {
+        "ok": True,
+        "available_copies": available,
+        "record": {
+            "book_id": book_id,
+            "reader_id": reader_id,
+            "borrow_date": record["borrow_date"],
+            "due_date": record["due_date"],
+            "returned": False,
+        },
+    }
+
+
+def handle_return_book(request, data):
+    book_id = request.get("book_id")
+    reader_id = request.get("reader_id")
+    if not is_valid_id(book_id) or not is_valid_id(reader_id):
+        return error("invalid_id")
+
+    return_date = parse_date(request.get("return_date"))
+    if return_date is None:
+        return error("invalid_date")
+
+    books = data["books"]
+    readers = data["readers"]
+    if book_id not in books:
+        return error("book_not_found")
+    if reader_id not in readers:
+        return error("reader_not_found")
+
+    borrows = data["borrows"]
+    target = find_active_borrow(borrows, book_id, reader_id)
+    if target is None:
+        return error("not_borrowed")
+
+    return_text = format_date(return_date)
+    target["returned"] = True
+    target["return_date"] = return_text
+
+    book = books[book_id]
+    available = book["total_copies"] - active_count(borrows, book_id)
+    return {
+        "ok": True,
+        "available_copies": available,
+        "record": {
+            "book_id": book_id,
+            "reader_id": reader_id,
+            "return_date": return_text,
+            "returned": True,
+        },
+    }
+
+
+def handle_list_borrowed(request, data):
+    reader_id = request.get("reader_id")
+    if not is_valid_id(reader_id):
+        return error("invalid_id")
+    if reader_id not in data["readers"]:
+        return error("reader_not_found")
+
+    books = data["books"]
+    borrows = []
+    for record in data["borrows"]:
+        if record.get("reader_id") != reader_id:
+            continue
+        if record.get("returned"):
+            continue
+        borrows.append(
+            {
+                "book_id": record.get("book_id"),
+                "title": book_title(books, record.get("book_id")),
+                "borrow_date": record.get("borrow_date"),
+                "due_date": record.get("due_date"),
+            }
+        )
+    return {"ok": True, "borrows": borrows}
+
+
+def handle_list_overdue(request, data):
+    reader_id = request.get("reader_id")
+    if reader_id is not None and not is_valid_id(reader_id):
+        return error("invalid_id")
+
+    date = parse_date(request.get("date"))
+    if date is None:
+        return error("invalid_date")
+
+    if reader_id is not None and reader_id not in data["readers"]:
+        return error("reader_not_found")
+
+    date_text = format_date(date)
+    books = data["books"]
+    overdue = []
+    for record in data["borrows"]:
+        if record.get("returned"):
+            continue
+        if reader_id is not None and record.get("reader_id") != reader_id:
+            continue
+        due_date = record.get("due_date")
+        if not isinstance(due_date, str) or due_date >= date_text:
+            continue
+        overdue.append(
+            {
+                "reader_id": record.get("reader_id"),
+                "book_id": record.get("book_id"),
+                "title": book_title(books, record.get("book_id")),
+                "borrow_date": record.get("borrow_date"),
+                "due_date": due_date,
+            }
+        )
+    return {"ok": True, "overdue": overdue}
+
+
+HANDLERS = {
+    "add_book": handle_add_book,
+    "add_reader": handle_add_reader,
+    "borrow": handle_borrow,
+    "return_book": handle_return_book,
+    "list_borrowed": handle_list_borrowed,
+    "list_overdue": handle_list_overdue,
+}
+
+
+def handle(request, data):
+    """处理一个请求，返回响应对象；只在全部校验通过后就地修改 data。"""
+    action = request.get("action")
+    if not isinstance(action, str):
+        return error("unknown_action")
+    handler = HANDLERS.get(action)
+    if handler is None:
+        return error("unknown_action")
+    return handler(request, data)
```

文件：main.py（added）
```diff
--- before/main.py
+++ after/main.py
@@ -0,0 +1,51 @@
+"""本地图书借阅工具入口：从 stdin 读取单个 JSON 请求并输出单个 JSON 响应。"""
+
+import json
+import sys
+
+from handlers import MUTATING_ACTIONS, handle
+from storage import load_library, save_library
+
+
+def emit(response):
+    """把响应对象以 UTF-8 JSON 单行写入 stdout。"""
+    text = json.dumps(response, ensure_ascii=False)
+    sys.stdout.write(text + "\n")
+    sys.stdout.flush()
+
+
+def parse_request(raw):
+    """解析 stdin 文本；空输入或非 JSON 对象返回 None。"""
+    if not isinstance(raw, str):
+        return None
+    if raw.strip() == "":
+        return None
+    try:
+        parsed = json.loads(raw)
+    except ValueError:
+        return None
+    if not isinstance(parsed, dict):
+        return None
+    return parsed
+
+
+def main():
+    raw = sys.stdin.read()
+    request = parse_request(raw)
+    if request is None:
+        emit({"ok": False, "error": "invalid_request"})
+        return 0
+
+    data = load_library()
+    action = request.get("action")
+    response = handle(request, data)
+
+    if response.get("ok") is True and isinstance(action, str) and action in MUTATING_ACTIONS:
+        save_library(data)
+
+    emit(response)
+    return 0
+
+
+if __name__ == "__main__":
+    sys.exit(main())
```

文件：storage.py（added）
```diff
--- before/storage.py
+++ after/storage.py
@@ -0,0 +1,117 @@
+"""library_data.json 的加载与写回。"""
+
+import json
+from pathlib import Path
+
+DATA_FILE = "library_data.json"
+
+
+def empty_library():
+    return {"next_seq": 1, "books": {}, "readers": {}, "borrows": []}
+
+
+def load_library(path=DATA_FILE):
+    """读取库数据；文件缺失、不可读或解析失败时视为空库。"""
+    try:
+        text = Path(path).read_text(encoding="utf-8")
+    except OSError:
+        return empty_library()
+    except ValueError:
+        return empty_library()
+    try:
+        raw = json.loads(text)
+    except ValueError:
+        return empty_library()
+    return normalize_library(raw)
+
+
+def normalize_library(raw):
+    """把任意读入结构规范化为可用的库对象。"""
+    library = empty_library()
+    if not isinstance(raw, dict):
+        return library
+
+    books_raw = raw.get("books")
+    if isinstance(books_raw, dict):
+        for key, value in books_raw.items():
+            if not isinstance(key, str) or key == "":
+                continue
+            if not isinstance(value, dict):
+                continue
+            title = value.get("title")
+            if not isinstance(title, str):
+                title = ""
+            total = value.get("total_copies")
+            if isinstance(total, bool) or not isinstance(total, int) or total < 1:
+                total = 1
+            library["books"][key] = {
+                "book_id": key,
+                "title": title,
+                "total_copies": total,
+            }
+
+    readers_raw = raw.get("readers")
+    if isinstance(readers_raw, dict):
+        for key, value in readers_raw.items():
+            if not isinstance(key, str) or key == "":
+                continue
+            if not isinstance(value, dict):
+                continue
+            name = value.get("name")
+            if not isinstance(name, str):
+                name = ""
+            library["readers"][key] = {"reader_id": key, "name": name}
+
+    borrows_raw = raw.get("borrows")
+    max_seq = 0
+    if isinstance(borrows_raw, list):
+        for value in borrows_raw:
+            if not isinstance(value, dict):
+                continue
+            book_id = value.get("book_id")
+            reader_id = value.get("reader_id")
+            borrow_date = value.get("borrow_date")
+            due_date = value.get("due_date")
+            if not isinstance(book_id, str) or book_id == "":
+                continue
+            if not isinstance(reader_id, str) or reader_id == "":
+                continue
+            if not isinstance(borrow_date, str) or not isinstance(due_date, str):
+                continue
+            returned = value.get("returned")
+            if not isinstance(returned, bool):
+                returned = False
+            return_date = value.get("return_date")
+            if not isinstance(return_date, str):
+                return_date = None
+            seq = value.get("seq")
+            if isinstance(seq, bool) or not isinstance(seq, int) or seq < 1:
+                seq = max_seq + 1
+            if seq > max_seq:
+                max_seq = seq
+            library["borrows"].append(
+                {
+                    "seq": seq,
+                    "book_id": book_id,
+                    "reader_id": reader_id,
+                    "borrow_date": borrow_date,
+                    "due_date": due_date,
+                    "returned": returned,
+                    "return_date": return_date,
+                }
+            )
+
+    next_seq = raw.get("next_seq")
+    if isinstance(next_seq, bool) or not isinstance(next_seq, int) or next_seq < 1:
+        next_seq = 1
+    if next_seq <= max_seq:
+        next_seq = max_seq + 1
+    library["next_seq"] = next_seq
+    return library
+
+
+def save_library(data, path=DATA_FILE):
+    """把完整库结构整体写回磁盘。"""
+    with Path(path).open("w", encoding="utf-8") as handle_file:
+        json.dump(data, handle_file, ensure_ascii=False, indent=2)
+        handle_file.write("\n")
```

文件：validators.py（added）
```diff
--- before/validators.py
+++ after/validators.py
@@ -0,0 +1,38 @@
+"""字段校验与日期工具。"""
+
+import datetime
+import re
+
+DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
+
+
+def is_valid_id(value):
+    """id 必须是非空字符串。"""
+    return isinstance(value, str) and len(value) > 0
+
+
+def is_valid_total_copies(value):
+    """total_copies 必须是 >= 1 的整数（布尔值不算）。"""
+    if isinstance(value, bool):
+        return False
+    return isinstance(value, int) and value >= 1
+
+
+def parse_date(value):
+    """严格解析 YYYY-MM-DD；非法或不存在返回 None。"""
+    if not isinstance(value, str):
+        return None
+    if DATE_PATTERN.match(value) is None:
+        return None
+    try:
+        return datetime.date.fromisoformat(value)
+    except ValueError:
+        return None
+
+
+def add_days(day, count):
+    return day + datetime.timedelta(days=count)
+
+
+def format_date(day):
+    return day.isoformat()
```
### 第 2 版

人工审查修订；没有模型API调用
结果：9/9；通过
失败原因：无


文件：README.md（modified）
```diff
--- before/README.md
+++ after/README.md
@@ -1,3 +1,21 @@
+# 人工审查修订版图书借阅工具
+
+本目录基于原始模型运行5452d526da7047cf的产物，经人工审查修改；不冒充Agent自动返工。原版及原8/8验收记录保留在相邻original目录及original-workflow.json。
+
+## 本次补充
+
+- 书名/姓名为必填非空白字符串，否则invalid_title/invalid_name；成功时去除首尾空白。
+- 编号拒绝纯空白；借阅期限计算溢出返回invalid_date。
+- 文件不存在可初始化；现有JSON损坏、字段类型错误、引用非法、读取失败均返回storage_error，不重置或覆盖。
+- 以library_data.json.tmp写入后Path.replace；保存失败返回storage_error并保留旧文件。只承诺单进程顺序使用下的替换，不承诺断电持久性或并发事务。
+- 沿用原规格允许合法还书日期早于借阅日期，不把这条已确认规则擅自更改。
+
+独立检查与原8项回归结果见上级results.json。包含新增质量要求，因此不能把原版新增检查失败回填成原8项验收失败。
+
+以下为原始协议说明，新增校验和存储规则以上述补充为准。
+
+---
+
 # local-library-lending

 一个零依赖（Python 3.10+ 标准库）的本地图书借阅管理工具。每次调用都是一个独立进程：
```

文件：handlers.py（modified）
```diff
--- before/handlers.py
+++ after/handlers.py
@@ -56,13 +56,17 @@
     if not is_valid_total_copies(total_copies):
         return error("invalid_total_copies")

+    title = request.get("title")
+    if not isinstance(title, str) or not title.strip():
+        return error("invalid_title")
+
     books = data["books"]
     if book_id in books:
         return error("duplicate_book_id")

     book = {
         "book_id": book_id,
-        "title": as_text(request.get("title")),
+        "title": title.strip(),
         "total_copies": total_copies,
     }
     books[book_id] = book
@@ -81,11 +85,15 @@
     if not is_valid_id(reader_id):
         return error("invalid_id")

+    name = request.get("name")
+    if not isinstance(name, str) or not name.strip():
+        return error("invalid_name")
+
     readers = data["readers"]
     if reader_id in readers:
         return error("duplicate_reader_id")

-    reader = {"reader_id": reader_id, "name": as_text(request.get("name"))}
+    reader = {"reader_id": reader_id, "name": name.strip()}
     readers[reader_id] = reader
     return {
         "ok": True,
@@ -118,7 +126,10 @@
     if active_count(borrows, book_id) >= book["total_copies"]:
         return error("no_copies_available")

-    due_date = add_days(borrow_date, LOAN_DAYS)
+    try:
+        due_date = add_days(borrow_date, LOAN_DAYS)
+    except (OverflowError, ValueError):
+        return error("invalid_date")
     seq = data.get("next_seq")
     if not isinstance(seq, int) or isinstance(seq, bool) or seq < 1:
         seq = 1
```

文件：main.py（modified）
```diff
--- before/main.py
+++ after/main.py
@@ -4,7 +4,7 @@
 import sys

 from handlers import MUTATING_ACTIONS, handle
-from storage import load_library, save_library
+from storage import StorageError, load_library, save_library


 def emit(response):
@@ -21,7 +21,7 @@
     if raw.strip() == "":
         return None
     try:
-        parsed = json.loads(raw)
+        parsed = json.loads(raw, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
     except ValueError:
         return None
     if not isinstance(parsed, dict):
@@ -36,12 +36,14 @@
         emit({"ok": False, "error": "invalid_request"})
         return 0

-    data = load_library()
-    action = request.get("action")
-    response = handle(request, data)
-
-    if response.get("ok") is True and isinstance(action, str) and action in MUTATING_ACTIONS:
-        save_library(data)
+    try:
+        data = load_library()
+        action = request.get("action")
+        response = handle(request, data)
+        if response.get("ok") is True and isinstance(action, str) and action in MUTATING_ACTIONS:
+            save_library(data)
+    except StorageError:
+        response = {"ok": False, "error": "storage_error"}

     emit(response)
     return 0
```

文件：storage.py（modified）
```diff
--- before/storage.py
+++ after/storage.py
@@ -1,117 +1,89 @@
-"""library_data.json 的加载与写回。"""
-
+"""人工审查修订：区分缺失和损坏，拒绝静默修复，以同目录临时文件替换保存。"""
 import json
 from pathlib import Path
+from validators import is_valid_id, is_valid_total_copies, parse_date, add_days, format_date

-DATA_FILE = "library_data.json"
+DATA_FILE = 'library_data.json'
+
+
+class StorageError(Exception):
+    pass


 def empty_library():
-    return {"next_seq": 1, "books": {}, "readers": {}, "borrows": []}
+    return {'next_seq': 1, 'books': {}, 'readers': {}, 'borrows': []}
+
+
+def nonempty(value):
+    return isinstance(value, str) and bool(value.strip())
+
+
+def normalize_library(raw):
+    # Validation preserves valid data as loaded. Never turn an invalid existing file into an empty one.
+    if not isinstance(raw, dict) or not {'next_seq', 'books', 'readers', 'borrows'} <= set(raw):
+        raise StorageError('invalid storage structure')
+    books, readers, borrows = raw['books'], raw['readers'], raw['borrows']
+    if not isinstance(books, dict) or not isinstance(readers, dict) or not isinstance(borrows, list):
+        raise StorageError('invalid storage collections')
+    for key, value in books.items():
+        if not is_valid_id(key) or not isinstance(value, dict) or value.get('book_id') != key or not nonempty(value.get('title')) or not is_valid_total_copies(value.get('total_copies')):
+            raise StorageError('invalid book')
+    for key, value in readers.items():
+        if not is_valid_id(key) or not isinstance(value, dict) or value.get('reader_id') != key or not nonempty(value.get('name')):
+            raise StorageError('invalid reader')
+    last_seq, active, seen_active = 0, {}, set()
+    for record in borrows:
+        if not isinstance(record, dict):
+            raise StorageError('invalid borrow')
+        book_id, reader_id, seq = record.get('book_id'), record.get('reader_id'), record.get('seq')
+        if not is_valid_id(book_id) or not is_valid_id(reader_id) or book_id not in books or reader_id not in readers:
+            raise StorageError('dangling borrow')
+        if type(seq) is not int or seq <= last_seq or not isinstance(record.get('returned'), bool):
+            raise StorageError('invalid sequence or returned state')
+        last_seq = seq
+        day, due = parse_date(record.get('borrow_date')), parse_date(record.get('due_date'))
+        if day is None or due is None or format_date(add_days(day, 14)) != record['due_date']:
+            raise StorageError('invalid borrow date')
+        if record['returned']:
+            if parse_date(record.get('return_date')) is None:
+                raise StorageError('invalid return date')
+        else:
+            if record.get('return_date') is not None or (book_id, reader_id) in seen_active:
+                raise StorageError('invalid active borrow')
+            seen_active.add((book_id, reader_id))
+            active[book_id] = active.get(book_id, 0) + 1
+    if type(raw['next_seq']) is not int or raw['next_seq'] <= last_seq:
+        raise StorageError('invalid next_seq')
+    if any(count > books[key]['total_copies'] for key, count in active.items()):
+        raise StorageError('invalid inventory')
+    return raw


 def load_library(path=DATA_FILE):
-    """读取库数据；文件缺失、不可读或解析失败时视为空库。"""
     try:
-        text = Path(path).read_text(encoding="utf-8")
-    except OSError:
+        text = Path(path).read_text(encoding='utf-8')
+    except FileNotFoundError:
         return empty_library()
-    except ValueError:
-        return empty_library()
+    except (OSError, UnicodeError) as exc:
+        raise StorageError('cannot read storage') from exc
     try:
-        raw = json.loads(text)
-    except ValueError:
-        return empty_library()
-    return normalize_library(raw)
-
-
-def normalize_library(raw):
-    """把任意读入结构规范化为可用的库对象。"""
-    library = empty_library()
-    if not isinstance(raw, dict):
-        return library
-
-    books_raw = raw.get("books")
-    if isinstance(books_raw, dict):
-        for key, value in books_raw.items():
-            if not isinstance(key, str) or key == "":
-                continue
-            if not isinstance(value, dict):
-                continue
-            title = value.get("title")
-            if not isinstance(title, str):
-                title = ""
-            total = value.get("total_copies")
-            if isinstance(total, bool) or not isinstance(total, int) or total < 1:
-                total = 1
-            library["books"][key] = {
-                "book_id": key,
-                "title": title,
-                "total_copies": total,
-            }
-
-    readers_raw = raw.get("readers")
-    if isinstance(readers_raw, dict):
-        for key, value in readers_raw.items():
-            if not isinstance(key, str) or key == "":
-                continue
-            if not isinstance(value, dict):
-                continue
-            name = value.get("name")
-            if not isinstance(name, str):
-                name = ""
-            library["readers"][key] = {"reader_id": key, "name": name}
-
-    borrows_raw = raw.get("borrows")
-    max_seq = 0
-    if isinstance(borrows_raw, list):
-        for value in borrows_raw:
-            if not isinstance(value, dict):
-                continue
-            book_id = value.get("book_id")
-            reader_id = value.get("reader_id")
-            borrow_date = value.get("borrow_date")
-            due_date = value.get("due_date")
-            if not isinstance(book_id, str) or book_id == "":
-                continue
-            if not isinstance(reader_id, str) or reader_id == "":
-                continue
-            if not isinstance(borrow_date, str) or not isinstance(due_date, str):
-                continue
-            returned = value.get("returned")
-            if not isinstance(returned, bool):
-                returned = False
-            return_date = value.get("return_date")
-            if not isinstance(return_date, str):
-                return_date = None
-            seq = value.get("seq")
-            if isinstance(seq, bool) or not isinstance(seq, int) or seq < 1:
-                seq = max_seq + 1
-            if seq > max_seq:
-                max_seq = seq
-            library["borrows"].append(
-                {
-                    "seq": seq,
-                    "book_id": book_id,
-                    "reader_id": reader_id,
-                    "borrow_date": borrow_date,
-                    "due_date": due_date,
-                    "returned": returned,
-                    "return_date": return_date,
-                }
-            )
-
-    next_seq = raw.get("next_seq")
-    if isinstance(next_seq, bool) or not isinstance(next_seq, int) or next_seq < 1:
-        next_seq = 1
-    if next_seq <= max_seq:
-        next_seq = max_seq + 1
-    library["next_seq"] = next_seq
-    return library
+        raw = json.loads(text, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
+        return normalize_library(raw)
+    except (ValueError, TypeError, KeyError, OverflowError) as exc:
+        raise StorageError('corrupted storage') from exc


 def save_library(data, path=DATA_FILE):
-    """把完整库结构整体写回磁盘。"""
-    with Path(path).open("w", encoding="utf-8") as handle_file:
-        json.dump(data, handle_file, ensure_ascii=False, indent=2)
-        handle_file.write("\n")
+    target = Path(path)
+    temporary = target.with_name(target.name + '.tmp')
+    try:
+        body = json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
+        temporary.write_text(body, encoding='utf-8')
+        temporary.replace(target)
+    except (OSError, ValueError, TypeError, UnicodeError) as exc:
+        try:
+            if temporary.is_file():
+                temporary.unlink()
+        except OSError:
+            pass
+        raise StorageError('cannot save storage') from exc
```

文件：validators.py（modified）
```diff
--- before/validators.py
+++ after/validators.py
@@ -8,7 +8,7 @@

 def is_valid_id(value):
     """id 必须是非空字符串。"""
-    return isinstance(value, str) and len(value) > 0
+    return isinstance(value, str) and bool(value.strip())


 def is_valid_total_copies(value):
```

## 独立评测

评测编号：library-audit；模式：human_reviewed
评测结果：通过；与流程验收状态分别记录。
套件 SHA256：1b3747380824cdc58626bc82f143cd3b8f85c39fdd2bbe3713390aa42525f9c3
独立用例：21/21
- C1 重复编号不覆盖原值、跨闰月应还日期：通过
- C2 库存耗尽不写入，其他读者不能借出：通过
- C3 重复借阅、重复归还拒绝，归还后可再次借出：通过
- C4 应还当日不逾期，次日逾期且按读者过滤：通过
- C5 不同图书互不影响，跨进程保持借阅顺序：通过
- C6 错误日期、未知图书与读者不改变库存：通过
- C7 布尔值不能充当库存或编号：通过
- C8 不存在读者不能查询：通过
- V1 缺少书名必须拒绝：通过
- V2 空白和非文本书名必须拒绝：通过
- V3 缺少读者姓名必须拒绝：通过
- V4 空白和非文本姓名必须拒绝：通过
- V5 纯空白编号必须拒绝：通过
- V6 日期溢出返回错误而非崩溃：通过
- V7 保留原规格的还书日期规则，不额外收紧：通过
- S1 JSON损坏时拒绝新增并保留原字节：通过
- S2 错误根结构不能被当成空库：通过
- S3 损坏字段不能静默修正并写回：通过
- S4 悬空借阅记录拒绝加载：通过
- S5 写临时文件失败保留原库并返回JSON：通过
- S6 数据路径不可读时明确失败：通过

## 已记录阶段耗时


## 限制与解释

通过只表示满足当前验收集，不保证所有输入正确。独立评测结果应另行查看。
模型生成的需求及用例可能遗漏用户意图；需求编号关联用于追踪，不能证明语义正确。
执行使用本机 Python，范围检查不是操作系统级沙箱。
取消与恢复以节点/检查点为单位；不能恢复某个模型请求内部的执行。
未恢复异常：无
