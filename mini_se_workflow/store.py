from __future__ import annotations

import io
import json
import re
import zipfile
from pathlib import Path


class RunStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def directory(self, run_id: str) -> Path:
        if not isinstance(run_id, str) or not re.fullmatch(r"[0-9a-f]{16}", run_id):
            raise ValueError("运行编号无效。")
        directory = self.root / run_id
        if directory.is_symlink() or directory.resolve().parent != self.root:
            raise ValueError("运行目录无效。")
        return directory

    def save(self, state: dict) -> None:
        directory = self.directory(state["run_id"])
        directory.mkdir(exist_ok=True)
        temporary = directory / "workflow.tmp"
        temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(directory / "workflow.json")

    def load(self, run_id: str) -> dict:
        path = self.directory(run_id) / "workflow.json"
        if not path.is_file():
            raise FileNotFoundError("运行记录不存在。")
        return json.loads(path.read_text(encoding="utf-8"))

    def revision(self, run_id: str, number: int, files: dict, report: dict) -> None:
        directory = self.directory(run_id) / f"revision-{number}"
        project = directory / "project"
        project.mkdir(parents=True, exist_ok=True)
        for name, content in files.items():
            (project / name).write_text(content, encoding="utf-8")
        (directory / "validation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    def history(self) -> list[dict]:
        summaries = []
        for path in self.root.glob("*/workflow.json"):
            try:
                state = self.load(path.parent.name)
                summaries.append({key: state.get(key) for key in ("run_id", "task", "mode", "status", "created_at", "repair_count")})
            except (ValueError, OSError):
                continue
        return sorted(summaries, key=lambda s: s["created_at"] or "", reverse=True)[:50]

    def archive(self, run_id: str) -> bytes:
        state = self.load(run_id)
        if state["status"] == "running" or not state["files"]:
            raise ValueError("本次运行尚无可下载的最终项目。")
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, source in state["files"].items():
                archive.writestr(name, source.encode("utf-8"))
            archive.writestr("_workflow/workflow.json", json.dumps(state, ensure_ascii=False, indent=2))
            archive.writestr("_workflow/acceptance.json", json.dumps(state["specification"], ensure_ascii=False, indent=2))
            archive.writestr("_workflow/design.json", json.dumps(state["design"], ensure_ascii=False, indent=2))
        return stream.getvalue()
