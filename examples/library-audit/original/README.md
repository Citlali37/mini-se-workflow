# local-library-lending

一个零依赖（Python 3.10+ 标准库）的本地图书借阅管理工具。每次调用都是一个独立进程：
从 stdin 读取一个 JSON 请求，执行一次操作，向 stdout 输出一个 JSON 响应，退出码始终为 0。
数据持久化在当前工作目录下的相对路径 `library_data.json`。

## 使用方法

```bash
python main.py
```

然后从标准输入传入一个 JSON 对象（通常通过管道或重定向）。输出是单行 UTF-8 JSON。

```bash
# Linux / macOS
echo '{"action":"add_book","book_id":"B1","title":"算法导论","total_copies":2}' | python main.py

# Windows PowerShell
'{"action":"add_book","book_id":"B1","title":"算法导论","total_copies":2}' | python main.py
```

## 响应信封

* 成功：`{"ok": true, ...}`
* 失败：`{"ok": false, "error": "<错误码>"}`

stdin 为空、不是合法 JSON 或不是 JSON 对象时返回 `{"ok": false, "error": "invalid_request"}`。

## 动作与请求示例

### add_book

请求：`{"action":"add_book","book_id":"B1","title":"算法导论","total_copies":2}`

成功：`{"ok":true,"book":{"book_id":"B1","title":"算法导论","total_copies":2}}`

错误：`invalid_id`、`invalid_total_copies`、`duplicate_book_id`。

### add_reader

请求：`{"action":"add_reader","reader_id":"R1","name":"张三"}`

成功：`{"ok":true,"reader":{"reader_id":"R1","name":"张三"}}`

错误：`invalid_id`、`duplicate_reader_id`。

### borrow

请求：`{"action":"borrow","book_id":"B1","reader_id":"R1","borrow_date":"2024-03-01"}`

成功：`{"ok":true,"available_copies":1,"record":{"book_id":"B1","reader_id":"R1","borrow_date":"2024-03-01","due_date":"2024-03-15","returned":false}}`

错误：`invalid_id`、`invalid_date`、`book_not_found`、`reader_not_found`、`already_borrowed`、`no_copies_available`。

### return_book

请求：`{"action":"return_book","book_id":"B1","reader_id":"R1","return_date":"2024-03-05"}`

成功：`{"ok":true,"available_copies":2,"record":{"book_id":"B1","reader_id":"R1","return_date":"2024-03-05","returned":true}}`

错误：`invalid_id`、`invalid_date`、`book_not_found`、`reader_not_found`、`not_borrowed`（含重复归还）。

### list_borrowed

请求：`{"action":"list_borrowed","reader_id":"R1"}`

成功：`{"ok":true,"borrows":[{"book_id":"B1","title":"算法导论","borrow_date":"2024-03-01","due_date":"2024-03-15"}]}`

只返回未归还（`returned=false`）的记录，按借阅登记顺序（seq）升序。错误：`invalid_id`、`reader_not_found`。

### list_overdue

请求：`{"action":"list_overdue","date":"2024-03-16"}` 或 `{"action":"list_overdue","date":"2024-03-16","reader_id":"R1"}`

成功：`{"ok":true,"overdue":[{"reader_id":"R1","book_id":"B1","title":"算法导论","borrow_date":"2024-03-01","due_date":"2024-03-15"}]}`

判定条件：未归还且 `due_date < date`（应还日期当天不算逾期）。不传 `reader_id` 时返回全部读者，按借阅登记顺序升序。
错误：`invalid_date`、`invalid_id`、`reader_not_found`。

### 其他

无法识别、缺失或非字符串的 `action` 返回 `{"ok":false,"error":"unknown_action"}`。

## 业务规则

* `book_id` / `reader_id` 必须是非空字符串，否则 `invalid_id`。
* `total_copies` 必须是 ≥ 1 的整数（布尔值不算），否则 `invalid_total_copies`。
* 日期必须严格为 `YYYY-MM-DD` 且是真实存在的公历日期（`2024-02-30`、`2024/01/01` 均非法），否则 `invalid_date`。
* 借阅期限固定 14 天：`due_date = borrow_date + 14 天`。
* 可借库存 `available_copies = total_copies − 该图书未归还的借阅记录数`；归还后库存恢复。
* 同一读者对同一本图书已有未归还借阅时，再次借阅返回 `already_borrowed`（优先于 `no_copies_available`）。
* 库存不足（未归还数等于 `total_copies`）时返回 `no_copies_available`，且不产生任何数据变更。
* `return_date` 只校验为合法日期，不要求晚于 `borrow_date`。
* 错误判定优先级：`invalid_id` → `invalid_date` → `book_not_found` → `reader_not_found` → 业务冲突（`duplicate_book_id`/`duplicate_reader_id`/`already_borrowed`/`no_copies_available`/`not_borrowed`）。
* 任何失败请求都不会修改已保存的数据，只有成功的写操作（add_book / add_reader / borrow / return_book）才写回文件。

## 存储格式

数据保存在当前工作目录下的 `library_data.json`（UTF-8）。文件不存在、不可读或 JSON 解析失败时按空库处理。

```json
{
  "next_seq": 2,
  "books": {
    "B1": {"book_id": "B1", "title": "算法导论", "total_copies": 2}
  },
  "readers": {
    "R1": {"reader_id": "R1", "name": "张三"}
  },
  "borrows": [
    {
      "seq": 1,
      "book_id": "B1",
      "reader_id": "R1",
      "borrow_date": "2024-03-01",
      "due_date": "2024-03-15",
      "returned": false,
      "return_date": null
    }
  ]
}
```

已归还的记录保留在 `borrows` 中（`returned=true` 且有 `return_date`），但不再占用库存，也不会出现在未归还列表或逾期列表中。
