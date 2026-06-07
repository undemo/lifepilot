from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCAN_DIRS = [ROOT / "backend" / "app", ROOT / "frontend"]
FORBIDDEN = [
    (re.compile(r"/api/mock\b"), "old mock path /api/mock"),
    (re.compile(r"/api/plans/create\b"), "old plan path /api/plans/create"),
    (re.compile(r"\bcreate_order\b"), "old ToolAction type create_order"),
    (re.compile(r"\bevent_type[\"']?\s*[:=]\s*[\"'](mock_call|api_log|verifier|executor)[\"']"), "invalid TraceLog event_type"),
    (re.compile(r"\bfailure_injection\b"), "failure_injection in ordinary runtime code"),
    (re.compile(r"chain_of_thought|api_key|API Key"), "sensitive prompt/runtime field"),
    (re.compile(r"已真实|真实(支付|订座|微信|短信|锁票|票务)成功|实时抓取成功"), "misleading real-world execution copy"),
]
ALLOWLIST = {
    ROOT / "frontend" / "app" / "page.tsx",
    ROOT / "frontend" / "app" / "execution" / "[executionId]" / "page.tsx",
    ROOT / "frontend" / "components" / "debug" / "DebugTracePanel.tsx",
    ROOT / "backend" / "app" / "services" / "plan_generator.py",
    ROOT / "backend" / "app" / "services" / "schema_validator.py",
    ROOT / "backend" / "app" / "services" / "intent_parser.py",
    ROOT / "backend" / "app" / "services" / "logging_service.py",
    ROOT / "backend" / "app" / "services" / "llm_client.py",
    ROOT / "backend" / "app" / "services" / "qwen_client.py",
    ROOT / "backend" / "app" / "core" / "constants.py",
    ROOT / "frontend" / "app" / "debug" / "traces" / "[traceId]" / "page.tsx",
}


def main() -> int:
    findings: list[str] = []
    for base in SCAN_DIRS:
        for path in base.rglob("*"):
            if not path.is_file() or "node_modules" in path.parts or ".next" in path.parts or "__pycache__" in path.parts:
                continue
            if "e2e" in path.parts:
                continue
            if path.suffix not in {".py", ".ts", ".tsx", ".js", ".mjs"}:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for pattern, label in FORBIDDEN:
                if pattern.search(text) and path not in ALLOWLIST:
                    findings.append(f"{path.relative_to(ROOT)}: {label}")
    if findings:
        print("Contract scan failed:")
        for item in findings:
            print(f"- {item}")
        return 1
    print("Contract scan passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
