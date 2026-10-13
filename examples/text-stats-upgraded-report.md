# Mini SE 交付报告

运行编号：c2f2d39fdc834073
状态：approved
模式：deepseek
已返工：1 / 2

## 原始需求与补充

开发一个文本统计工具。每次从标准输入接收 JSON 对象，包含 text 字段，统计并返回：包含空格和换行的总字符数 characters；连续 ASCII 字母或数字组成的英文单词数 words（例如 hello-world 是2个词）；按 splitlines() 计算的行数 lines（空字符串为0行）。正常输出包含 ok:true 和这三个整数。空文本应成功返回三个0。text 缺失或不是字符串时返回 ok:false,error:"invalid_text"。不需要保存数据，也不需要联网。请提供中文、英文、空文本、换行和无效输入的验收用例。

## 需求确认记录

确认时间：2026-10-13T03:37:35+00:00
规格修改/补充记录：1 条

## 需求追踪

- R1：从 stdin 读取一个 JSON 对象，处理后将单个 JSON 对象写入 stdout，进程退出码为 0。；文件：main.py, README.md；验收：A1, A6
- R2：输出 characters 字段，值为 text 字符串的总字符数，包含空格和换行。；文件：main.py, text_stats.py, README.md；验收：A1, A2, A3, A5, A6
- R3：输出 words 字段，值为 text 中连续 ASCII 字母或数字组成的片段数量；例如 hello-world 计为 2 个词。；文件：main.py, text_stats.py, README.md；验收：A1, A2, A3, A5, A6, A7
- R4：输出 lines 字段，值为 text.splitlines() 的结果长度；空字符串返回 0 行。；文件：main.py, text_stats.py, README.md；验收：A1, A2, A3, A5, A6, A7
- R5：text 为空字符串时，返回 {"ok": true, "characters": 0, "words": 0, "lines": 0}。；文件：main.py, text_stats.py, README.md；验收：A4
- R6：text 缺失或不是字符串时，返回 {"ok": false, "error": "invalid_text"}。；文件：main.py, text_stats.py, README.md；验收：A8, A9, A10

## 每版验收与修改

### 第 1 版

编码输出格式未通过校验。
结果：0/10；未通过
失败原因：编码结果必须完整包含设计中的全部文件，且不能增加未设计的文件。缺少：text_stats.py；未规划：无。

### 第 2 版

按设计完整实现三个文件：text_stats.py（纯统计逻辑）、main.py（stdin/stdout JSON 协议入口，引用本地模块）、README.md（协议与示例说明）。修复上一版缺失 text_stats.py 的问题，并实现 characters/words/lines 的精确语义与 invalid_text 错误路径。
结果：10/10；通过
失败原因：无


文件：README.md（added）
```diff
--- before/README.md
+++ after/README.md
@@ -0,0 +1,78 @@
+# text_stats_tool
+
+一个零依赖的本地文本统计工具，使用 Python 3.10+ 标准库实现。
+每次请求启动一个新进程：从 stdin 读取一个 JSON 对象，向 stdout 写出一个 JSON 对象，退出码恒为 0。
+
+## 运行方式
+
+```bash
+python main.py
+```
+
+stdin 传入一个 JSON 对象（可带尾随换行），stdout 只输出一个 JSON 对象，没有任何日志或提示信息。
+
+```bash
+echo '{"text": "hello world"}' | python main.py
+# {"ok": true, "characters": 11, "words": 2, "lines": 1}
+```
+
+## 请求字段
+
+| 字段 | 类型 | 说明 |
+| --- | --- | --- |
+| `text` | string | 要统计的文本。顶层其他字段一律忽略。 |
+
+## 响应
+
+成功：
+
+```json
+{"ok": true, "characters": 11, "words": 2, "lines": 1}
+```
+
+失败（`text` 缺失或不是字符串，例如 null、数字、布尔、数组、对象）：
+
+```json
+{"ok": false, "error": "invalid_text"}
+```
+
+两种情况下退出码都是 0。
+
+## 统计定义
+
+- `characters`：`len(text)`，即 Python 字符个数，空格、制表符、换行各计 1。
+- `words`：正则 `[A-Za-z0-9]+` 在 `text` 上的非重叠匹配数量。
+  即只有连续的 ASCII 字母或数字才算一个词；连字符 `-`、下划线 `_`、标点、空白、换行以及
+  所有非 ASCII 字符（如中文、日文、重音字母）都是分隔符。
+  例如 `hello-world` 计为 2 个词，`你好世界` 计为 0 个词。
+- `lines`：`len(text.splitlines())`，与 Python 的 `str.splitlines()` 语义一致。
+  空字符串返回 0 行，`"a\nb\n"` 返回 2 行。
+
+类型校验顺序：只要 `text` 缺失或不是 `str`，立即返回 `invalid_text`，不做任何统计。
+
+## 请求 / 响应示例
+
+| 输入 | 输出 |
+| --- | --- |
+| `{"text": "hello world"}` | `{"ok": true, "characters": 11, "words": 2, "lines": 1}` |
+| `{"text": "hello-world"}` | `{"ok": true, "characters": 11, "words": 2, "lines": 1}` |
+| `{"text": "你好世界"}` | `{"ok": true, "characters": 4, "words": 0, "lines": 1}` |
+| `{"text": ""}` | `{"ok": true, "characters": 0, "words": 0, "lines": 0}` |
+| `{"text": "a\nb\n"}` | `{"ok": true, "characters": 4, "words": 2, "lines": 2}` |
+| `{"text": "第一行\nsecond line 42\n"}` | `{"ok": true, "characters": 19, "words": 3, "lines": 2}` |
+| `{"text": "  hello,  world!  "}` | `{"ok": true, "characters": 18, "words": 2, "lines": 1}` |
+| `{"text": 123}` | `{"ok": false, "error": "invalid_text"}` |
+| `{}` | `{"ok": false, "error": "invalid_text"}` |
+| `{"text": null}` | `{"ok": false, "error": "invalid_text"}` |
+
+## 模块结构
+
+- `main.py`：入口与 JSON 协议层，负责读取 stdin、调用统计逻辑、写出 stdout 并返回退出码 0。
+- `text_stats.py`：纯统计逻辑（`is_valid_text`、`count_characters`、`count_words`、`count_lines`、
+  `compute_stats`、`build_error`），不读写任何文件或标准流。
+
+## 其他说明
+
+- 无网络、无第三方依赖、无子进程、无系统命令。
+- 每次请求都是独立新进程，不保存任何持久化数据。
+- 文本以 UTF-8 读写，输出使用 `ensure_ascii=False`，中文按原样输出。
```

文件：main.py（added）
```diff
--- before/main.py
+++ after/main.py
@@ -0,0 +1,60 @@
+"""Entry point and stdin/stdout JSON protocol layer for the text statistics tool.
+
+Usage:
+    python main.py
+
+Reads a single JSON object from stdin, writes a single JSON object to stdout,
+and always exits with status code 0.
+"""
+
+import json
+import sys
+
+import text_stats
+
+
+def read_request(stream=sys.stdin):
+    """Read the whole input stream and parse it as JSON.
+
+    Returns the parsed object, or None when the payload is not valid JSON.
+    """
+    raw = stream.read()
+    if raw is None:
+        return None
+    try:
+        return json.loads(raw)
+    except Exception:
+        return None
+
+
+def write_response(payload, stream=sys.stdout):
+    """Write exactly one JSON object (plus newline) to the output stream."""
+    stream.write(json.dumps(payload, ensure_ascii=False) + "\n")
+    stream.flush()
+
+
+def handle_request(request):
+    """Turn a parsed request object into a response object."""
+    if not isinstance(request, dict):
+        return text_stats.build_error("invalid_text")
+    if "text" not in request:
+        return text_stats.build_error("invalid_text")
+    text = request["text"]
+    if not text_stats.is_valid_text(text):
+        return text_stats.build_error("invalid_text")
+    return text_stats.compute_stats(text)
+
+
+def main(argv=None):
+    """Execute one request and return the process exit code (always 0)."""
+    request = read_request(sys.stdin)
+    try:
+        response = handle_request(request)
+    except Exception:
+        response = text_stats.build_error("invalid_text")
+    write_response(response)
+    return 0
+
+
+if __name__ == "__main__":
+    sys.exit(main())
```

文件：text_stats.py（added）
```diff
--- before/text_stats.py
+++ after/text_stats.py
@@ -0,0 +1,46 @@
+"""Pure text statistics helpers (no IO, no side effects).
+
+Definitions:
+    characters = len(text)                       (spaces, tabs and newlines included)
+    words      = number of [A-Za-z0-9]+ matches   (hyphen/underscore/punctuation are separators)
+    lines      = len(text.splitlines())           (empty string -> 0)
+"""
+
+import re
+
+WORD_PATTERN = re.compile(r"[A-Za-z0-9]+")
+
+
+def is_valid_text(value):
+    """Return True only when value is a str."""
+    return isinstance(value, str)
+
+
+def count_characters(text):
+    """Total number of characters, including spaces and newlines."""
+    return len(text)
+
+
+def count_words(text):
+    """Number of runs of ASCII letters or digits."""
+    return len(WORD_PATTERN.findall(text))
+
+
+def count_lines(text):
+    """Number of lines, following Python's str.splitlines() semantics."""
+    return len(text.splitlines())
+
+
+def compute_stats(text):
+    """Build the success response for a validated text string."""
+    return {
+        "ok": True,
+        "characters": count_characters(text),
+        "words": count_words(text),
+        "lines": count_lines(text),
+    }
+
+
+def build_error(error_code):
+    """Build the failure response for the given error code."""
+    return {"ok": False, "error": error_code}
```

## 已记录阶段耗时

- 需求 Agent：14214 ms
- 设计 Agent：8398 ms
- 验收执行器：2 ms
- 编码 Agent：11254 ms
- Workflow：719 ms

## 限制与解释

通过只表示满足当前验收集，不保证所有输入正确。独立评测结果应另行查看。
模型生成的需求及用例可能遗漏用户意图；需求编号关联用于追踪，不能证明语义正确。
执行使用本机 Python，范围检查不是操作系统级沙箱。
取消与恢复以节点/检查点为单位；不能恢复某个模型请求内部的执行。
未恢复异常：无
