from __future__ import annotations

import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
LOGS = REPORTS / "logs"
SCREENSHOTS = REPORTS / "screenshots"
DEMO_NOW = "2026-05-21T13:30:00+08:00"


def ensure_dirs() -> None:
    LOGS.mkdir(parents=True, exist_ok=True)
    SCREENSHOTS.mkdir(parents=True, exist_ok=True)


def run_command(name: str, cmd: list[str], cwd: Path, env: dict[str, str] | None = None) -> dict:
    started = time.time()
    log_path = LOGS / f"{name}.log"
    with log_path.open("w", encoding="utf-8") as log:
        log.write(f"$ {' '.join(cmd)}\n")
        log.flush()
        process = subprocess.run(cmd, cwd=str(cwd), env=env, stdout=log, stderr=subprocess.STDOUT, text=True)
    return {
        "name": name,
        "cmd": cmd,
        "returncode": process.returncode,
        "seconds": round(time.time() - started, 2),
        "log": str(log_path.relative_to(ROOT)),
    }


def start_process(name: str, cmd: list[str], cwd: Path, env: dict[str, str]) -> subprocess.Popen:
    log_path = LOGS / f"{name}.log"
    log = log_path.open("w", encoding="utf-8")
    log.write(f"$ {' '.join(cmd)}\n")
    log.flush()
    return subprocess.Popen(cmd, cwd=str(cwd), env=env, stdout=log, stderr=subprocess.STDOUT, text=True)


def wait_http(url: str, timeout: int = 60) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if 200 <= response.status < 500:
                    return True
        except (urllib.error.URLError, TimeoutError):
            time.sleep(1)
    return False


def free_port(preferred: int) -> int:
    for port in [preferred, *range(preferred + 1, preferred + 30)]:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise RuntimeError("no free local port for backend")


def stop_process(process: subprocess.Popen | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        if os.name != "nt":
            process.send_signal(signal.SIGKILL)
        process.kill()


def write_reports(results: list[dict], backend_ready: bool, frontend_ready: bool) -> None:
    passed = backend_ready and frontend_ready and all(item["returncode"] == 0 for item in results)
    payload = {
        "passed": passed,
        "backend_ready": backend_ready,
        "frontend_ready": frontend_ready,
        "demo_now": DEMO_NOW,
        "results": results,
        "screenshots_dir": str(SCREENSHOTS.relative_to(ROOT)),
    }
    (REPORTS / "p0_frontend_smoke_report.md").write_text(
        "\n".join(
            [
                "# P0 Frontend Smoke Report",
                "",
                f"- passed: {passed}",
                f"- backend_ready: {backend_ready}",
                f"- frontend_ready: {frontend_ready}",
                f"- screenshots: `{SCREENSHOTS.relative_to(ROOT)}`",
                "",
                "## Steps",
                *[f"- {item['name']}: rc={item['returncode']} time={item['seconds']}s log=`{item['log']}`" for item in results],
                "",
            ]
        ),
        encoding="utf-8",
    )
    (REPORTS / "p0_fix_report.md").write_text(
        "\n".join(
            [
                "# P0 Fix Report",
                "",
                "## Fixed",
                "",
                "- Added ordinary-page PlanContract ViewModel mapping and Chinese label projection.",
                "- Aggregated ToolTracePanel into six user-visible stages.",
                "- Added solo mood-relief intent, constraints, candidate ranking, and rhythm explanations.",
                "- Stabilized afternoon window with fixed demo now support.",
                "- Generated and persisted friend_group candidate plans for real voting.",
                "- Added P0 backend/API tests, Playwright E2E, contract scan, mock data validation, and this smoke runner.",
                "",
                f"Smoke passed: {passed}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    if not (REPORTS / "p0_e2e_result.json").exists():
        (REPORTS / "p0_e2e_result.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    ensure_dirs()
    env = os.environ.copy()
    smoke_data_dir = REPORTS / "tmp_backend_data"
    if smoke_data_dir.exists():
        shutil.rmtree(smoke_data_dir)
    shutil.copytree(ROOT / "backend" / "data", smoke_data_dir)
    env["PYTHONPATH"] = str(ROOT / "backend")
    env["LIFEPILOT_DATA_DIR"] = str(smoke_data_dir)
    env["LIFEPILOT_DEMO_NOW"] = DEMO_NOW
    env["NEXT_PUBLIC_LIFEPILOT_DEMO_NOW"] = DEMO_NOW
    backend_port = free_port(8000)
    env["BACKEND_ORIGIN"] = f"http://127.0.0.1:{backend_port}"

    results: list[dict] = []
    backend = None
    frontend = None
    backend_ready = False
    frontend_ready = False
    try:
        backend = start_process("backend", [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(backend_port)], ROOT, env)
        backend_ready = wait_http(f"http://127.0.0.1:{backend_port}/health", 60)
        if not backend_ready:
            results.append({"name": "backend_start", "cmd": ["uvicorn"], "returncode": 1, "seconds": 60, "log": "reports/logs/backend.log"})
            return 1

        results.append(run_command("npm_install", ["npm", "install"], ROOT / "frontend", env))
        if results[-1]["returncode"] == 0:
            results.append(run_command("playwright_install", ["npx", "playwright", "install", "chromium"], ROOT / "frontend", env))

        frontend = start_process("frontend", ["npm", "run", "dev", "--", "--hostname", "127.0.0.1", "--port", "3000"], ROOT / "frontend", env)
        frontend_ready = wait_http("http://127.0.0.1:3000", 90)
        if not frontend_ready:
            results.append({"name": "frontend_start", "cmd": ["npm", "run", "dev"], "returncode": 1, "seconds": 90, "log": "reports/logs/frontend.log"})
            return 1

        results.append(run_command("backend_p0_tests", [sys.executable, "scripts/run_backend_p0_tests.py"], ROOT, env))
        results.append(run_command("contract_scan", [sys.executable, "scripts/contract_scan.py"], ROOT, env))
        results.append(run_command("validate_mock_data", [sys.executable, "scripts/validate_mock_data.py"], ROOT, env))
        results.append(run_command("e2e", ["npm", "run", "e2e"], ROOT / "frontend", env))
        return 0 if all(item["returncode"] == 0 for item in results) else 1
    finally:
        stop_process(frontend)
        stop_process(backend)
        write_reports(results, backend_ready, frontend_ready)


if __name__ == "__main__":
    raise SystemExit(main())
