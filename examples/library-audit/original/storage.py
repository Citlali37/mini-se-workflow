"""library_data.json 的加载与写回。"""

import json
from pathlib import Path

DATA_FILE = "library_data.json"


def empty_library():
    return {"next_seq": 1, "books": {}, "readers": {}, "borrows": []}


def load_library(path=DATA_FILE):
    """读取库数据；文件缺失、不可读或解析失败时视为空库。"""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return empty_library()
    except ValueError:
        return empty_library()
    try:
        raw = json.loads(text)
    except ValueError:
        return empty_library()
    return normalize_library(raw)


def normalize_library(raw):
    """把任意读入结构规范化为可用的库对象。"""
    library = empty_library()
    if not isinstance(raw, dict):
        return library

    books_raw = raw.get("books")
    if isinstance(books_raw, dict):
        for key, value in books_raw.items():
            if not isinstance(key, str) or key == "":
                continue
            if not isinstance(value, dict):
                continue
            title = value.get("title")
            if not isinstance(title, str):
                title = ""
            total = value.get("total_copies")
            if isinstance(total, bool) or not isinstance(total, int) or total < 1:
                total = 1
            library["books"][key] = {
                "book_id": key,
                "title": title,
                "total_copies": total,
            }

    readers_raw = raw.get("readers")
    if isinstance(readers_raw, dict):
        for key, value in readers_raw.items():
            if not isinstance(key, str) or key == "":
                continue
            if not isinstance(value, dict):
                continue
            name = value.get("name")
            if not isinstance(name, str):
                name = ""
            library["readers"][key] = {"reader_id": key, "name": name}

    borrows_raw = raw.get("borrows")
    max_seq = 0
    if isinstance(borrows_raw, list):
        for value in borrows_raw:
            if not isinstance(value, dict):
                continue
            book_id = value.get("book_id")
            reader_id = value.get("reader_id")
            borrow_date = value.get("borrow_date")
            due_date = value.get("due_date")
            if not isinstance(book_id, str) or book_id == "":
                continue
            if not isinstance(reader_id, str) or reader_id == "":
                continue
            if not isinstance(borrow_date, str) or not isinstance(due_date, str):
                continue
            returned = value.get("returned")
            if not isinstance(returned, bool):
                returned = False
            return_date = value.get("return_date")
            if not isinstance(return_date, str):
                return_date = None
            seq = value.get("seq")
            if isinstance(seq, bool) or not isinstance(seq, int) or seq < 1:
                seq = max_seq + 1
            if seq > max_seq:
                max_seq = seq
            library["borrows"].append(
                {
                    "seq": seq,
                    "book_id": book_id,
                    "reader_id": reader_id,
                    "borrow_date": borrow_date,
                    "due_date": due_date,
                    "returned": returned,
                    "return_date": return_date,
                }
            )

    next_seq = raw.get("next_seq")
    if isinstance(next_seq, bool) or not isinstance(next_seq, int) or next_seq < 1:
        next_seq = 1
    if next_seq <= max_seq:
        next_seq = max_seq + 1
    library["next_seq"] = next_seq
    return library


def save_library(data, path=DATA_FILE):
    """把完整库结构整体写回磁盘。"""
    with Path(path).open("w", encoding="utf-8") as handle_file:
        json.dump(data, handle_file, ensure_ascii=False, indent=2)
        handle_file.write("\n")
