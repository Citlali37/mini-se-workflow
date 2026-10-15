"""图书借阅工具的业务逻辑：动作分发、校验顺序、库存与逾期计算。"""

from validators import add_days, format_date, is_valid_id, is_valid_total_copies, parse_date

MUTATING_ACTIONS = {"add_book", "add_reader", "borrow", "return_book"}
LOAN_DAYS = 14


def error(code):
    return {"ok": False, "error": code}


def as_text(value):
    """title/name 缺失或非字符串时按空字符串处理。"""
    if isinstance(value, str):
        return value
    return ""


def active_count(borrows, book_id):
    """该图书当前未归还的借阅数量。"""
    total = 0
    for record in borrows:
        if record.get("book_id") == book_id and not record.get("returned"):
            total += 1
    return total


def find_active_borrow(borrows, book_id, reader_id):
    """查找该 (book_id, reader_id) 最早的未归还记录，没有则返回 None。"""
    for record in borrows:
        if record.get("book_id") != book_id:
            continue
        if record.get("reader_id") != reader_id:
            continue
        if record.get("returned"):
            continue
        return record
    return None


def book_title(books, book_id):
    book = books.get(book_id)
    if isinstance(book, dict):
        title = book.get("title")
        if isinstance(title, str):
            return title
    return ""


def handle_add_book(request, data):
    book_id = request.get("book_id")
    if not is_valid_id(book_id):
        return error("invalid_id")
    total_copies = request.get("total_copies")
    if not is_valid_total_copies(total_copies):
        return error("invalid_total_copies")

    title = request.get("title")
    if not isinstance(title, str) or not title.strip():
        return error("invalid_title")

    books = data["books"]
    if book_id in books:
        return error("duplicate_book_id")

    book = {
        "book_id": book_id,
        "title": title.strip(),
        "total_copies": total_copies,
    }
    books[book_id] = book
    return {
        "ok": True,
        "book": {
            "book_id": book["book_id"],
            "title": book["title"],
            "total_copies": book["total_copies"],
        },
    }


def handle_add_reader(request, data):
    reader_id = request.get("reader_id")
    if not is_valid_id(reader_id):
        return error("invalid_id")

    name = request.get("name")
    if not isinstance(name, str) or not name.strip():
        return error("invalid_name")

    readers = data["readers"]
    if reader_id in readers:
        return error("duplicate_reader_id")

    reader = {"reader_id": reader_id, "name": name.strip()}
    readers[reader_id] = reader
    return {
        "ok": True,
        "reader": {"reader_id": reader["reader_id"], "name": reader["name"]},
    }


def handle_borrow(request, data):
    book_id = request.get("book_id")
    reader_id = request.get("reader_id")
    if not is_valid_id(book_id) or not is_valid_id(reader_id):
        return error("invalid_id")

    borrow_date = parse_date(request.get("borrow_date"))
    if borrow_date is None:
        return error("invalid_date")

    books = data["books"]
    readers = data["readers"]
    if book_id not in books:
        return error("book_not_found")
    if reader_id not in readers:
        return error("reader_not_found")

    borrows = data["borrows"]
    if find_active_borrow(borrows, book_id, reader_id) is not None:
        return error("already_borrowed")

    book = books[book_id]
    if active_count(borrows, book_id) >= book["total_copies"]:
        return error("no_copies_available")

    try:
        due_date = add_days(borrow_date, LOAN_DAYS)
    except (OverflowError, ValueError):
        return error("invalid_date")
    seq = data.get("next_seq")
    if not isinstance(seq, int) or isinstance(seq, bool) or seq < 1:
        seq = 1
    record = {
        "seq": seq,
        "book_id": book_id,
        "reader_id": reader_id,
        "borrow_date": format_date(borrow_date),
        "due_date": format_date(due_date),
        "returned": False,
        "return_date": None,
    }
    borrows.append(record)
    data["next_seq"] = seq + 1

    available = book["total_copies"] - active_count(borrows, book_id)
    return {
        "ok": True,
        "available_copies": available,
        "record": {
            "book_id": book_id,
            "reader_id": reader_id,
            "borrow_date": record["borrow_date"],
            "due_date": record["due_date"],
            "returned": False,
        },
    }


def handle_return_book(request, data):
    book_id = request.get("book_id")
    reader_id = request.get("reader_id")
    if not is_valid_id(book_id) or not is_valid_id(reader_id):
        return error("invalid_id")

    return_date = parse_date(request.get("return_date"))
    if return_date is None:
        return error("invalid_date")

    books = data["books"]
    readers = data["readers"]
    if book_id not in books:
        return error("book_not_found")
    if reader_id not in readers:
        return error("reader_not_found")

    borrows = data["borrows"]
    target = find_active_borrow(borrows, book_id, reader_id)
    if target is None:
        return error("not_borrowed")

    return_text = format_date(return_date)
    target["returned"] = True
    target["return_date"] = return_text

    book = books[book_id]
    available = book["total_copies"] - active_count(borrows, book_id)
    return {
        "ok": True,
        "available_copies": available,
        "record": {
            "book_id": book_id,
            "reader_id": reader_id,
            "return_date": return_text,
            "returned": True,
        },
    }


def handle_list_borrowed(request, data):
    reader_id = request.get("reader_id")
    if not is_valid_id(reader_id):
        return error("invalid_id")
    if reader_id not in data["readers"]:
        return error("reader_not_found")

    books = data["books"]
    borrows = []
    for record in data["borrows"]:
        if record.get("reader_id") != reader_id:
            continue
        if record.get("returned"):
            continue
        borrows.append(
            {
                "book_id": record.get("book_id"),
                "title": book_title(books, record.get("book_id")),
                "borrow_date": record.get("borrow_date"),
                "due_date": record.get("due_date"),
            }
        )
    return {"ok": True, "borrows": borrows}


def handle_list_overdue(request, data):
    reader_id = request.get("reader_id")
    if reader_id is not None and not is_valid_id(reader_id):
        return error("invalid_id")

    date = parse_date(request.get("date"))
    if date is None:
        return error("invalid_date")

    if reader_id is not None and reader_id not in data["readers"]:
        return error("reader_not_found")

    date_text = format_date(date)
    books = data["books"]
    overdue = []
    for record in data["borrows"]:
        if record.get("returned"):
            continue
        if reader_id is not None and record.get("reader_id") != reader_id:
            continue
        due_date = record.get("due_date")
        if not isinstance(due_date, str) or due_date >= date_text:
            continue
        overdue.append(
            {
                "reader_id": record.get("reader_id"),
                "book_id": record.get("book_id"),
                "title": book_title(books, record.get("book_id")),
                "borrow_date": record.get("borrow_date"),
                "due_date": due_date,
            }
        )
    return {"ok": True, "overdue": overdue}


HANDLERS = {
    "add_book": handle_add_book,
    "add_reader": handle_add_reader,
    "borrow": handle_borrow,
    "return_book": handle_return_book,
    "list_borrowed": handle_list_borrowed,
    "list_overdue": handle_list_overdue,
}


def handle(request, data):
    """处理一个请求，返回响应对象；只在全部校验通过后就地修改 data。"""
    action = request.get("action")
    if not isinstance(action, str):
        return error("unknown_action")
    handler = HANDLERS.get(action)
    if handler is None:
        return error("unknown_action")
    return handler(request, data)
