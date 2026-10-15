"""人工审查修订：区分缺失和损坏，拒绝静默修复，以同目录临时文件替换保存。"""
import json
from pathlib import Path
from validators import is_valid_id, is_valid_total_copies, parse_date, add_days, format_date

DATA_FILE = 'library_data.json'


class StorageError(Exception):
    pass


def empty_library():
    return {'next_seq': 1, 'books': {}, 'readers': {}, 'borrows': []}


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def normalize_library(raw):
    # Validation preserves valid data as loaded. Never turn an invalid existing file into an empty one.
    if not isinstance(raw, dict) or not {'next_seq', 'books', 'readers', 'borrows'} <= set(raw):
        raise StorageError('invalid storage structure')
    books, readers, borrows = raw['books'], raw['readers'], raw['borrows']
    if not isinstance(books, dict) or not isinstance(readers, dict) or not isinstance(borrows, list):
        raise StorageError('invalid storage collections')
    for key, value in books.items():
        if not is_valid_id(key) or not isinstance(value, dict) or value.get('book_id') != key or not nonempty(value.get('title')) or not is_valid_total_copies(value.get('total_copies')):
            raise StorageError('invalid book')
    for key, value in readers.items():
        if not is_valid_id(key) or not isinstance(value, dict) or value.get('reader_id') != key or not nonempty(value.get('name')):
            raise StorageError('invalid reader')
    last_seq, active, seen_active = 0, {}, set()
    for record in borrows:
        if not isinstance(record, dict):
            raise StorageError('invalid borrow')
        book_id, reader_id, seq = record.get('book_id'), record.get('reader_id'), record.get('seq')
        if not is_valid_id(book_id) or not is_valid_id(reader_id) or book_id not in books or reader_id not in readers:
            raise StorageError('dangling borrow')
        if type(seq) is not int or seq <= last_seq or not isinstance(record.get('returned'), bool):
            raise StorageError('invalid sequence or returned state')
        last_seq = seq
        day, due = parse_date(record.get('borrow_date')), parse_date(record.get('due_date'))
        if day is None or due is None or format_date(add_days(day, 14)) != record['due_date']:
            raise StorageError('invalid borrow date')
        if record['returned']:
            if parse_date(record.get('return_date')) is None:
                raise StorageError('invalid return date')
        else:
            if record.get('return_date') is not None or (book_id, reader_id) in seen_active:
                raise StorageError('invalid active borrow')
            seen_active.add((book_id, reader_id))
            active[book_id] = active.get(book_id, 0) + 1
    if type(raw['next_seq']) is not int or raw['next_seq'] <= last_seq:
        raise StorageError('invalid next_seq')
    if any(count > books[key]['total_copies'] for key, count in active.items()):
        raise StorageError('invalid inventory')
    return raw


def load_library(path=DATA_FILE):
    try:
        text = Path(path).read_text(encoding='utf-8')
    except FileNotFoundError:
        return empty_library()
    except (OSError, UnicodeError) as exc:
        raise StorageError('cannot read storage') from exc
    try:
        raw = json.loads(text, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
        return normalize_library(raw)
    except (ValueError, TypeError, KeyError, OverflowError) as exc:
        raise StorageError('corrupted storage') from exc


def save_library(data, path=DATA_FILE):
    target = Path(path)
    temporary = target.with_name(target.name + '.tmp')
    try:
        body = json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
        temporary.write_text(body, encoding='utf-8')
        temporary.replace(target)
    except (OSError, ValueError, TypeError, UnicodeError) as exc:
        try:
            if temporary.is_file():
                temporary.unlink()
        except OSError:
            pass
        raise StorageError('cannot save storage') from exc
