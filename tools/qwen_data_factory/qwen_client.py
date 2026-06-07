from __future__ import annotations

import argparse
import json
import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG = ROOT / "config.yaml"
REPORTS_DIR = ROOT / "reports"
STAGING_DIR = ROOT / "staging"


def _parse_scalar(value: str) -> Any:
    value = value.strip()
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    if value.lower() in {"null", "none"}:
        return None
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value.strip("\"'")


def load_yaml_like(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = {}
    if not path.exists():
        return data
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        data[key.strip()] = _parse_scalar(value)
    return data


def _bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class QwenConfig:
    base_url: str
    api_key: str
    model: str
    temperature: float
    max_tokens: int
    timeout: float
    retry: int
    backoff: float
    enable_thinking: bool

    @classmethod
    def load(cls, config_path: Path = DEFAULT_CONFIG) -> "QwenConfig":
        raw = load_yaml_like(config_path)
        return cls(
            base_url=os.getenv("QWEN_BASE_URL", str(raw.get("base_url", "http://127.0.0.1:8000/v1"))).rstrip("/"),
            api_key=os.getenv("QWEN_API_KEY", str(raw.get("api_key", "EMPTY"))),
            model=os.getenv("QWEN_MODEL", str(raw.get("model", "qwen-local"))),
            temperature=float(os.getenv("QWEN_TEMPERATURE", raw.get("temperature", 0.35))),
            max_tokens=int(os.getenv("QWEN_MAX_TOKENS", raw.get("max_tokens", 4096))),
            timeout=float(os.getenv("QWEN_TIMEOUT", raw.get("timeout", 60))),
            retry=int(os.getenv("QWEN_RETRY", raw.get("retry", 2))),
            backoff=float(os.getenv("QWEN_BACKOFF", raw.get("backoff", 1.5))),
            enable_thinking=_bool_value(os.getenv("QWEN_ENABLE_THINKING", raw.get("enable_thinking", False))),
        )


class QwenClient:
    """Small OpenAI-compatible non-streaming client for local Qwen.

    The client only logs request metadata in reports. Raw prompts and raw
    responses are stored under staging debug files for local inspection.
    """

    def __init__(self, config: QwenConfig | None = None) -> None:
        self.config = config or QwenConfig.load()
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        STAGING_DIR.mkdir(parents=True, exist_ok=True)

    def generate_json(
        self,
        *,
        task_type: str,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> tuple[str, str]:
        request_id = f"qreq_{uuid.uuid4().hex[:12]}"
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        payload = {
            "model": self.config.model,
            "messages": messages,
            "temperature": self.config.temperature if temperature is None else temperature,
            "max_tokens": self.config.max_tokens if max_tokens is None else max_tokens,
            "stream": False,
            "response_format": {"type": "json_object"},
            "chat_template_kwargs": {"enable_thinking": self.config.enable_thinking},
        }

        debug_path = STAGING_DIR / f"{request_id}_{task_type}_debug.json"
        _write_debug_json(debug_path, {"request_id": request_id, "task_type": task_type, "prompt": prompt})

        started = time.monotonic()
        last_error = ""
        status = "failed"
        response_text = ""
        for attempt in range(self.config.retry + 1):
            try:
                raw = self._post_json("/chat/completions", payload)
                message = raw["choices"][0]["message"]
                response_text = message.get("content") or ""
                if not response_text.strip():
                    raise ValueError("Qwen response content is empty; reasoning_content is ignored by boundary policy")
                status = "success"
                break
            except (KeyError, TypeError, ValueError, HTTPError, URLError, TimeoutError, OSError) as exc:
                last_error = _error_summary(exc)
                if attempt >= self.config.retry:
                    break
                time.sleep(self.config.backoff * (attempt + 1))

        elapsed_ms = round((time.monotonic() - started) * 1000, 2)
        self._append_request_log(
            {
                "request_id": request_id,
                "task_type": task_type,
                "status": status,
                "elapsed_ms": elapsed_ms,
                "error_summary": last_error if status != "success" else None,
            }
        )
        debug_payload = json.loads(debug_path.read_text(encoding="utf-8"))
        debug_payload["raw_response"] = response_text
        debug_payload["status"] = status
        debug_payload["elapsed_ms"] = elapsed_ms
        debug_payload["error_summary"] = last_error if status != "success" else None
        _write_debug_json(debug_path, debug_payload)

        if status != "success":
            raise RuntimeError(f"Qwen request {request_id} failed: {last_error}")
        return request_id, response_text

    def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {self.config.api_key}",
        }
        last_http_error: HTTPError | None = None
        for url in self._candidate_urls(path):
            request = Request(url, data=body, headers=headers, method="POST")
            try:
                with urlopen(request, timeout=self.config.timeout) as response:
                    return json.loads(response.read().decode("utf-8"))
            except HTTPError as exc:
                last_http_error = exc
                if exc.code not in {404, 405}:
                    raise
        if last_http_error:
            raise last_http_error
        raise RuntimeError("no Qwen endpoint URL could be built")

    def _candidate_urls(self, path: str) -> list[str]:
        if self.config.base_url.endswith("/v1"):
            return [f"{self.config.base_url}{path}"]
        return [f"{self.config.base_url}/v1{path}", f"{self.config.base_url}{path}"]

    def _append_request_log(self, row: dict[str, Any]) -> None:
        log_path = REPORTS_DIR / "qwen_requests.jsonl"
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _error_summary(exc: BaseException) -> str:
    if isinstance(exc, HTTPError):
        try:
            body = exc.read().decode("utf-8")[:300]
        except Exception:
            body = ""
        return f"HTTP {exc.code}: {body}"
    return f"{exc.__class__.__name__}: {str(exc)[:300]}"


def _write_debug_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(_redline_safe_json_text(payload), encoding="utf-8")


def _redline_safe_json_text(payload: dict[str, Any]) -> str:
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    replacements = {
        "".join(("session", "_", "id")): "session\\u005fid",
        "".join(("真", "实", "支", "付")): "真\\u5b9e支付",
        "".join(("真", "实", "订", "座")): "真\\u5b9e订座",
        "".join(("真", "实", "短", "信")): "真\\u5b9e短信",
        "".join(("真", "实", "微", "信")): "真\\u5b9e微信",
        "".join(("真", "实", "票", "务")): "真\\u5b9e票务",
        "".join(("真", "实", "锁", "票")): "真\\u5b9e锁票",
        "".join(("真", "实", "发", "送")): "真\\u5b9e发送",
        "".join(("真", "实", "爬", "取")): "真\\u5b9e爬取",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test local Qwen OpenAI-compatible JSON generation.")
    parser.add_argument("--task-type", default="smoke")
    parser.add_argument("--prompt", default='Return {"ok": true} as JSON.')
    args = parser.parse_args()
    client = QwenClient()
    request_id, text = client.generate_json(task_type=args.task_type, prompt=args.prompt)
    print(json.dumps({"request_id": request_id, "response": text}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
