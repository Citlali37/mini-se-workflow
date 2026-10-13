from storage import load, save


def handle(request):
    action = request.get("action")
    if action not in ("add", "list", "complete", "delete"):
        return {"ok": False, "error": "unknown_action"}
    try:
        data = load()
    except ValueError:
        return {"ok": False, "error": "storage_error"}
    if action == "list":
        return {"ok": True, "tasks": data["tasks"]}
    if action == "add":
        title = request.get("title")
        if not isinstance(title, str) or not title.strip():
            return {"ok": False, "error": "empty_title"}
        task = {"id": data["next_id"], "title": title.strip(), "completed": False}
        data["next_id"] += 1
        data["tasks"].append(task)
        save(data)
        return {"ok": True, "task": task}
    task_id = request.get("id")
    if type(task_id) is not int or task_id <= 0:
        return {"ok": False, "error": "invalid_id"}
    for task in data["tasks"]:
        if task["id"] == task_id:
            if action == "complete":
                task["completed"] = True
                result = {"ok": True, "task": task}
            else:
                data["tasks"].remove(task)
                result = {"ok": True, "deleted_id": task_id}
            save(data)
            return result
    return {"ok": False, "error": "not_found"}
