from __future__ import annotations

import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .demo import DEMO_TASK
from .models import WorkflowExecutionError
from .workflow import MiniSEWorkflow


class BusyError(RuntimeError):
    pass


class WebApp:
    def __init__(self, workflow: MiniSEWorkflow) -> None:
        self.workflow = workflow
        self._run_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._state = None
        self._error = ""

    def update(self, state: dict) -> None:
        with self._state_lock:
            self._state = state

    def status(self) -> dict:
        with self._state_lock:
            return {"ok": True, "busy": self._run_lock.locked(), "state": self._state, "error": self._error, "mode": self.workflow.mode}

    def start(self, task: object, example_id: object = None) -> None:
        if not isinstance(task, str) or not task.strip() or len(task) > 6000:
            raise ValueError("需求必须是1到6000字符的文本。")
        if example_id not in (None, "todo"):
            raise ValueError("示例类型无效。")
        if example_id == "todo" and task.strip() != DEMO_TASK:
            raise ValueError("修改示例需求后，应作为自定义需求运行。")
        if self.workflow.mode == "demo" and task.strip() != DEMO_TASK:
            raise ValueError("离线演示仅支持预置待办事项需求；自由需求请使用 DeepSeek 模式。")
        if not self._run_lock.acquire(blocking=False):
            raise BusyError("已有任务正在运行，请等待完成。")
        with self._state_lock:
            self._state = None
            self._error = ""

        def execute() -> None:
            try:
                self.workflow.run(task, example_id=example_id, on_update=self.update)
            except WorkflowExecutionError as exc:
                self.update(exc.state.to_dict())
                with self._state_lock:
                    self._error = str(exc)
            except Exception as exc:
                with self._state_lock:
                    self._error = str(exc)
            finally:
                self._run_lock.release()

        try:
            threading.Thread(target=execute, daemon=True).start()
        except Exception:
            self._run_lock.release()
            raise


class LocalServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def create_server(workflow: MiniSEWorkflow, port: int = 8002) -> LocalServer:
    app = WebApp(workflow)
    index = (Path(__file__).with_name("static") / "index.html").read_bytes()

    class Handler(BaseHTTPRequestHandler):
        server_version = "MiniSE/0.1"

        def valid_host(self) -> bool:
            host = self.headers.get("Host", "").lower()
            actual_port = self.server.server_address[1]
            return host in {f"127.0.0.1:{actual_port}", f"localhost:{actual_port}"}

        def send_body(self, status: int, body: bytes, content_type: str, filename: str | None = None) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            if filename:
                self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def send_json(self, status: int, data: dict) -> None:
            self.send_body(status, json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

        def do_GET(self) -> None:
            if not self.valid_host():
                self.send_json(403, {"ok": False, "error": "仅支持本机访问。"})
                return
            path = urlparse(self.path).path
            try:
                if path == "/":
                    self.send_body(200, index, "text/html; charset=utf-8")
                elif path == "/api/health":
                    self.send_json(200, {"ok": True, "mode": workflow.mode, "example_task": DEMO_TASK, "max_repairs": workflow.max_repairs})
                elif path == "/api/status":
                    self.send_json(200, app.status())
                elif path == "/api/runs":
                    self.send_json(200, {"ok": True, "runs": workflow.store.history()})
                elif path.startswith("/api/runs/"):
                    self.send_json(200, {"ok": True, "state": workflow.store.load(path.removeprefix("/api/runs/"))})
                elif path.startswith("/api/download/"):
                    run_id = path.removeprefix("/api/download/")
                    archive = workflow.store.archive(run_id)
                    self.send_body(200, archive, "application/zip", f"mini-se-{run_id}.zip")
                elif path == "/favicon.ico":
                    self.send_body(204, b"", "image/x-icon")
                else:
                    self.send_json(404, {"ok": False, "error": "页面不存在。"})
            except FileNotFoundError as exc:
                self.send_json(404, {"ok": False, "error": str(exc)})
            except ValueError as exc:
                self.send_json(400, {"ok": False, "error": str(exc)})
            except OSError:
                self.send_json(500, {"ok": False, "error": "无法读取运行记录。"})

        def do_POST(self) -> None:
            if not self.valid_host():
                self.send_json(403, {"ok": False, "error": "仅支持本机访问。"})
                return
            origin = self.headers.get("Origin")
            if origin and origin != f"http://{self.headers['Host']}":
                self.send_json(403, {"ok": False, "error": "请求来源无效。"})
                return
            if urlparse(self.path).path != "/api/run":
                self.send_json(404, {"ok": False, "error": "接口不存在。"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 1 <= length <= 32768:
                    raise ValueError("请求体大小无效。")
                if self.headers.get("Content-Type", "").split(";")[0].strip().lower() != "application/json":
                    raise ValueError("请提交 JSON 请求。")
                self.connection.settimeout(10)
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                if not isinstance(payload, dict):
                    raise ValueError("请求必须是 JSON 对象。")
                app.start(payload.get("task"), payload.get("example_id"))
                self.send_json(202, {"ok": True, "message": "任务已开始。"})
            except BusyError as exc:
                self.send_json(409, {"ok": False, "error": str(exc)})
            except (ValueError, UnicodeDecodeError) as exc:
                self.send_json(400, {"ok": False, "error": str(exc)})
            except TimeoutError:
                self.send_json(408, {"ok": False, "error": "读取请求超时。"})

        def log_message(self, format: str, *args) -> None:
            # Polling stays quiet; errors remain visible to the browser.
            pass

    server = LocalServer(("127.0.0.1", port), Handler)
    server.app = app
    return server


def run_web(workflow: MiniSEWorkflow, port: int = 8002, open_browser: bool = False) -> None:
    server = create_server(workflow, port)
    url = f"http://127.0.0.1:{server.server_address[1]}"
    print(f"Mini SE 已启动：{url}（{'离线演示' if workflow.mode == 'demo' else 'DeepSeek'}）")
    print("按 Ctrl+C 停止服务。")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        print("\n服务已停止。")
    finally:
        server.server_close()
