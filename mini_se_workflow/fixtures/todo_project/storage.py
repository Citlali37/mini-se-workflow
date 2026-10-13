import json
from pathlib import Path


DATA_FILE = Path("tasks.json")


def load():
    if not DATA_FILE.exists():
        return {"next_id": 1, "tasks": []}
    value = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not isinstance(value.get("tasks"), list):
        raise ValueError("invalid data")
    if type(value.get("next_id")) is not int or value["next_id"] < 1:
        raise ValueError("invalid next id")
    for task in value["tasks"]:
        if not isinstance(task, dict) or type(task.get("id")) is not int:
            raise ValueError("invalid task")
        if not isinstance(task.get("title"), str) or type(task.get("completed")) is not bool:
            raise ValueError("invalid task fields")
    return value


def save(data):
    temporary = Path("tasks.tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(DATA_FILE)
