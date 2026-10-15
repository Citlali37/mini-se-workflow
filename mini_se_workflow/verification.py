"""Reproduce repository checks without credentials or model requests."""
from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parent.parent


def check_report(name: str, report: dict) -> None:
    """Check fixture expectations, including the original library's expected failures."""
    if name == "evaluation":
        rows = report["results"]
        valid = (report["mode"] == "fixture" and len(rows) == 6
                 and len({r["id"] for r in rows}) == 6
                 and all(r["success"] is True for r in rows)
                 and report["http_request_count"] == 0)
    elif name == "comparison":
        rows = report["trials"]
        valid = (report["mode"] == "comparison-fixture" and len(rows) == 6
                 and {(r["task"], r["arm"]) for r in rows}
                 == {(t, a) for t in ("text-stats", "ledger", "library") for a in ("single", "multi")}
                 and all(r["success"] is True and r["http_requests"] == 0 for r in rows))
    elif name == "library-audit":
        versions = report["versions"]
        valid = all(versions[v]["regression"]["passed"] is True
                    and versions[v]["regression"]["passed_count"] == 8
                    and versions[v]["regression"]["total"] == 8
                    for v in ("original", "reviewed"))
        for version, expected in (("original", 9), ("reviewed", 21)):
            result = versions[version]["independent"]
            valid = (valid and result["passed_count"] == expected and result["total"] == 21
                     and result["passed"] is (expected == 21)
                     and len(result["cases"]) == 21
                     and sum(c["passed"] is True for c in result["cases"]) == expected)
    else:
        raise ValueError("Unknown check: " + name)
    if not valid:
        raise ValueError("Unexpected offline results for " + name + "; inspect the JSON and log.")


def run_check(name: str, arguments: list[str], directory: Path,
              artifact: Path | None = None) -> dict:
    command = [sys.executable, "-X", "utf8", *arguments]
    log = directory / (name + ".log")
    started = time.monotonic()
    error = ""
    code = None
    try:
        with log.open("w", encoding="utf-8") as stream:
            result = subprocess.run(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT,
                                    timeout=600, check=False)
        code = result.returncode
        if code != 0:
            error = "Process exited with " + str(code)
        elif artifact is not None:
            check_report(name, json.loads(artifact.read_text(encoding="utf-8")))
    except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as exc:
        error = str(exc)
    return {"name": name, "command": command, "returncode": code,
            "passed": code == 0 and not error, "error": error,
            "duration_seconds": round(time.monotonic() - started, 3),
            "log": str(log.relative_to(ROOT)) if log.is_relative_to(ROOT) else str(log),
            "artifact": str(artifact.relative_to(ROOT)) if artifact and artifact.is_relative_to(ROOT)
            else str(artifact) if artifact else None}


def main() -> int:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    directory = ROOT / "outputs" / "review" / (stamp + "-" + uuid4().hex[:8])
    directory.mkdir(parents=True)
    plan = [
        ("unittest", ["-m", "unittest", "discover", "-s", "tests", "-v"], None),
        ("evaluation", ["-m", "mini_se_workflow.evaluation", "--output", str(directory / "evaluation.json"),
                        "--run-root", str(directory / "evaluation-runs")], directory / "evaluation.json"),
        ("comparison", ["-m", "mini_se_workflow.comparison", "--repeats", "1",
                        "--output", str(directory / "comparison.json"),
                        "--run-root", str(directory / "comparison-runs")], directory / "comparison.json"),
        ("library-audit", ["-m", "mini_se_workflow.library_audit", "--output",
                           str(directory / "library-audit.json")], directory / "library-audit.json"),
    ]
    summary = {"mode": "offline-repository-verification", "created_at": stamp,
               "description": "Checks code and fixed fixtures; does not measure model capability.",
               "expected_checks": [name for name, _, _ in plan],
               "completed": False, "passed": False, "checks": []}
    summary_path = directory / "summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    for name, arguments, artifact in plan:
        print("Running " + name + " ...", flush=True)
        result = run_check(name, arguments, directory, artifact)
        summary["checks"].append(result)
        summary["completed"] = len(summary["checks"]) == len(plan)
        summary["passed"] = summary["completed"] and all(item["passed"] for item in summary["checks"])
        summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print(name + ": " + ("PASS" if result["passed"] else "FAIL: " + result["error"]), flush=True)
    print("Evidence: " + str(directory), flush=True)
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
