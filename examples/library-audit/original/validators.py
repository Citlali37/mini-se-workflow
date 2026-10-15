"""字段校验与日期工具。"""

import datetime
import re

DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def is_valid_id(value):
    """id 必须是非空字符串。"""
    return isinstance(value, str) and len(value) > 0


def is_valid_total_copies(value):
    """total_copies 必须是 >= 1 的整数（布尔值不算）。"""
    if isinstance(value, bool):
        return False
    return isinstance(value, int) and value >= 1


def parse_date(value):
    """严格解析 YYYY-MM-DD；非法或不存在返回 None。"""
    if not isinstance(value, str):
        return None
    if DATE_PATTERN.match(value) is None:
        return None
    try:
        return datetime.date.fromisoformat(value)
    except ValueError:
        return None


def add_days(day, count):
    return day + datetime.timedelta(days=count)


def format_date(day):
    return day.isoformat()
