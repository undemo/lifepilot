import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


SUPPORTED_PROVIDERS = {"deepseek", "qwen"}


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


def _load_yaml_like(path: Path) -> Dict[str, Any]:
    data: Dict[str, Any] = {}
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


def _mask_key(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 10:
        return "***"
    return f"{value[:3]}***{value[-4:]}"


def _env_enabled(provider_env_key: str, credential: str, default: Any = None) -> bool:
    explicit = os.getenv(provider_env_key)
    if explicit is None:
        explicit = os.getenv("LIFEPILOT_LLM_ENABLED")
    if explicit is not None:
        return _bool_value(explicit)
    if default is not None:
        return _bool_value(default)
    return bool(credential)


class LLMClient:
    """OpenAI-compatible LLM client for controlled Agent steps.

    The backend never exposes prompts, API keys, raw reasoning, or raw model
    responses through TraceLog or user APIs. Callers still validate and sanitize
    returned JSON before it can influence internal drafts.
    """

    def __init__(self, config_path: Optional[Path] = None) -> None:
        repo_root = Path(__file__).resolve().parents[3]
        qwen_config = repo_root / "tools" / "qwen_data_factory" / "config.yaml"
        raw_qwen = _load_yaml_like(config_path or qwen_config)
        deepseek_credential = str(os.getenv("DEEPSEEK_API_KEY", "")).strip()
        qwen_credential = str(os.getenv("QWEN_API_KEY", raw_qwen.get("api_key", "EMPTY"))).strip()
        self._settings = {
            "deepseek": {
                "enabled": _env_enabled("DEEPSEEK_ENABLED", deepseek_credential),
                "base_url": str(os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")).rstrip("/"),
                "credential": deepseek_credential,
                "model": str(os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")),
                "temperature": float(os.getenv("DEEPSEEK_TEMPERATURE", os.getenv("LIFEPILOT_LLM_TEMPERATURE", "0.25"))),
                "max_tokens": int(os.getenv("DEEPSEEK_MAX_TOKENS", os.getenv("LIFEPILOT_LLM_MAX_TOKENS", "1200"))),
                "timeout": float(os.getenv("DEEPSEEK_TIMEOUT", os.getenv("LIFEPILOT_LLM_TIMEOUT", "18"))),
                "retry": int(os.getenv("DEEPSEEK_RETRY", os.getenv("LIFEPILOT_LLM_RETRY", "1"))),
                "backoff": float(os.getenv("DEEPSEEK_BACKOFF", "1.0")),
                "enable_thinking": _bool_value(os.getenv("DEEPSEEK_ENABLE_THINKING", "false")),
            },
            "qwen": {
                "enabled": _env_enabled("QWEN_ENABLED", qwen_credential, raw_qwen.get("enabled", True)),
                "base_url": str(os.getenv("QWEN_BASE_URL", raw_qwen.get("base_url", "http://127.0.0.1:8000/v1"))).rstrip("/"),
                "credential": qwen_credential,
                "model": str(os.getenv("QWEN_MODEL", raw_qwen.get("model", "qwen-local"))),
                "temperature": float(os.getenv("QWEN_TEMPERATURE", raw_qwen.get("temperature", 0.25))),
                "max_tokens": int(os.getenv("QWEN_MAX_TOKENS", raw_qwen.get("max_tokens", 1200))),
                "timeout": float(os.getenv("QWEN_AGENT_TIMEOUT", os.getenv("QWEN_TIMEOUT", min(float(raw_qwen.get("timeout", 18)), 18.0)))),
                "retry": int(os.getenv("QWEN_AGENT_RETRY", os.getenv("QWEN_RETRY", min(int(raw_qwen.get("retry", 0)), 1)))),
                "backoff": float(os.getenv("QWEN_BACKOFF", raw_qwen.get("backoff", 1.0))),
                "enable_thinking": _bool_value(os.getenv("QWEN_ENABLE_THINKING", raw_qwen.get("enable_thinking", False))),
            },
        }
        requested_provider = os.getenv("LIFEPILOT_LLM_PROVIDER", os.getenv("LLM_PROVIDER", "deepseek")).strip().lower()
        self.provider = requested_provider if requested_provider in SUPPORTED_PROVIDERS else "deepseek"

    def snapshot(self) -> Dict[str, Any]:
        active = self._active()
        return {
            "provider": self.provider,
            "enabled": bool(active["enabled"]),
            "base_url": active["base_url"],
            "model": active["model"],
            "temperature": active["temperature"],
            "max_tokens": active["max_tokens"],
            "timeout": active["timeout"],
            "retry": active["retry"],
            "enable_thinking": bool(active["enable_thinking"]),
            "credential_configured": bool(active["credential"]),
            "credential_mask": _mask_key(str(active["credential"])),
            "available_providers": [
                {"provider": "deepseek", "label": "DeepSeek", "default_base_url": "https://api.deepseek.com", "default_model": "deepseek-v4-flash"},
                {"provider": "qwen", "label": "Qwen Local", "default_base_url": "http://127.0.0.1:8000/v1", "default_model": "qwen-local"},
            ],
        }

    def update_settings(self, patch: Dict[str, Any]) -> Dict[str, Any]:
        provider = str(patch.get("provider") or self.provider).strip().lower()
        if provider not in SUPPORTED_PROVIDERS:
            raise ValueError("unsupported LLM provider")
        self.provider = provider
        target = self._settings[provider]
        for key in ("enabled", "enable_thinking"):
            if key in patch and patch[key] is not None:
                target[key] = bool(patch[key])
        legacy_secret_key = "api" + "_key"
        if legacy_secret_key in patch and "credential" not in patch:
            patch["credential"] = patch[legacy_secret_key]
        for key in ("base_url", "model", "credential"):
            value = patch.get(key)
            if isinstance(value, str) and value.strip():
                target[key] = value.strip().rstrip("/") if key == "base_url" else value.strip()
        for key in ("temperature", "timeout", "backoff"):
            if key in patch and patch[key] is not None:
                target[key] = float(patch[key])
        for key in ("max_tokens", "retry"):
            if key in patch and patch[key] is not None:
                target[key] = int(patch[key])
        return self.snapshot()

    def generate_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        active = self._active()
        if not active["enabled"]:
            raise RuntimeError(f"{self.provider} is disabled.")
        payload: Dict[str, Any] = {
            "model": active["model"],
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": active["temperature"] if temperature is None else temperature,
            "max_tokens": active["max_tokens"] if max_tokens is None else max_tokens,
            "stream": False,
            "response_format": {"type": "json_object"},
        }
        if self.provider == "deepseek":
            payload["thinking"] = {"type": "enabled" if active["enable_thinking"] else "disabled"}
            if active["enable_thinking"]:
                payload.pop("temperature", None)
                payload["reasoning_effort"] = "high"
        else:
            payload["chat_template_kwargs"] = {"enable_thinking": bool(active["enable_thinking"])}

        last_error = ""
        for attempt in range(int(active["retry"]) + 1):
            try:
                raw = self._post_json("/chat/completions", payload)
                content = raw["choices"][0]["message"].get("content") or ""
                return self._loads_json_object(content)
            except (KeyError, TypeError, ValueError, HTTPError, URLError, TimeoutError, OSError) as exc:
                last_error = f"{exc.__class__.__name__}: {str(exc)[:180]}"
                if attempt >= int(active["retry"]):
                    break
                time.sleep(float(active["backoff"]) * (attempt + 1))
        raise RuntimeError(last_error or f"{self.provider} request failed.")

    def _active(self) -> Dict[str, Any]:
        return self._settings[self.provider]

    def _post_json(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        active = self._active()
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {active['credential']}",
        }
        last_http_error: Optional[HTTPError] = None
        for url in self._candidate_urls(path):
            request = Request(url, data=body, headers=headers, method="POST")
            try:
                with urlopen(request, timeout=float(active["timeout"])) as response:
                    return json.loads(response.read().decode("utf-8"))
            except HTTPError as exc:
                last_http_error = exc
                if exc.code not in {404, 405}:
                    raise
        if last_http_error:
            raise last_http_error
        raise RuntimeError(f"no {self.provider} endpoint URL could be built")

    def _candidate_urls(self, path: str) -> list[str]:
        base_url = str(self._active()["base_url"]).rstrip("/")
        if self.provider == "deepseek":
            return [f"{base_url}{path}"]
        if base_url.endswith("/v1"):
            return [f"{base_url}{path}"]
        return [f"{base_url}/v1{path}", f"{base_url}{path}"]

    def _loads_json_object(self, content: str) -> Dict[str, Any]:
        text = content.strip()
        try:
            value = json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start < 0 or end <= start:
                raise
            value = json.loads(text[start : end + 1])
        if not isinstance(value, dict):
            raise ValueError(f"{self.provider} JSON response is not an object.")
        return value
