from __future__ import annotations

import contextvars
import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple

import httpx

from supportkit.config import load_platform

CALLS: "contextvars.ContextVar[Optional[List[Dict[str, Any]]]]" = contextvars.ContextVar("llm_calls", default=None)

OPENAI_COMPAT = {
    "openai": ("OPENAI_BASE_URL", "https://api.openai.com/v1", "OPENAI_API_KEY"),
    "groq": ("GROQ_BASE_URL", "https://api.groq.com/openai/v1", "GROQ_API_KEY"),
    "deepseek": ("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1", "DEEPSEEK_API_KEY"),
    "openrouter": ("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1", "OPENROUTER_API_KEY"),
    "custom": ("CUSTOM_BASE_URL", "http://localhost:8000/v1", "CUSTOM_API_KEY"),
}


class LLMError(RuntimeError):
    pass


def parse_spec(spec: str) -> Tuple[str, str]:
    spec = (spec or "").strip()
    if os.environ.get("LLM_FORCE"):
        spec = os.environ["LLM_FORCE"]
    if not spec:
        raise LLMError("empty model spec; set it in platform.yml or .env, for example ollama:qwen3:4b")
    if ":" not in spec:
        return spec, ""
    provider, model = spec.split(":", 1)
    return provider.lower(), model


def strip_think(text: str) -> str:
    return re.sub(r"<think>.*?</think>", "", text or "", flags=re.S).strip()


def _record(provider: str, model: str, started: float, usage: Dict[str, int]) -> None:
    calls = CALLS.get()
    if calls is not None:
        calls.append(
            {
                "provider": provider,
                "model": model,
                "ms": round((time.perf_counter() - started) * 1000, 1),
                "input_tokens": usage.get("input", 0),
                "output_tokens": usage.get("output", 0),
            }
        )


def _post(url: str, headers: Dict[str, str], payload: Dict[str, Any], timeout: float, retries: int = 2) -> Dict[str, Any]:
    last: Optional[Exception] = None
    for attempt in range(retries + 1):
        try:
            r = httpx.post(url, headers=headers, json=payload, timeout=timeout)
            if r.status_code in (429, 500, 502, 503, 504) and attempt < retries:
                time.sleep(1.5 * (attempt + 1))
                continue
            if r.status_code >= 400:
                raise LLMError(f"{url} returned {r.status_code}: {r.text[:300]}")
            return r.json()
        except httpx.TransportError as e:
            last = e
            if attempt < retries:
                time.sleep(1.0 * (attempt + 1))
                continue
    raise LLMError(f"cannot reach {url}: {last}. Is the provider running and configured in .env?")


def chat(
    spec: str,
    system: str,
    user: str,
    temperature: float = 0.0,
    json_mode: bool = False,
    max_tokens: int = 700,
    seed: Optional[int] = None,
) -> str:
    provider, model = parse_spec(spec)
    started = time.perf_counter()
    cfg = load_platform().llm.get("providers", {})
    timeout = float(cfg.get("timeout_s", 180))
    if provider == "mock":
        from supportkit.mock import mock_chat

        text = mock_chat(system, user, temperature, seed)
        _record(provider, model or "mock", started, {"input": len(system + user) // 4, "output": len(text) // 4})
        return text
    if provider == "ollama":
        host = (cfg.get("ollama", {}) or {}).get("host") or os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        payload: Dict[str, Any] = {
            "model": model,
            "stream": False,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        if seed is not None:
            payload["options"]["seed"] = seed
        if json_mode:
            payload["format"] = "json"
        if any(k in model.lower() for k in ("qwen3", "r1", "deepseek-r1")):
            payload["think"] = False
        data = _post(f"{host.rstrip('/')}/api/chat", {}, payload, timeout)
        text = strip_think((data.get("message") or {}).get("content", ""))
        _record(provider, model, started, {"input": data.get("prompt_eval_count", 0), "output": data.get("eval_count", 0)})
        return text
    if provider == "anthropic":
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise LLMError("ANTHROPIC_API_KEY is not set")
        payload = {
            "model": model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        if temperature and temperature > 0:
            payload["temperature"] = temperature
        base = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
        data = _post(
            f"{base.rstrip('/')}/v1/messages",
            {"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            payload,
            timeout,
        )
        text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
        usage = data.get("usage", {})
        _record(provider, model, started, {"input": usage.get("input_tokens", 0), "output": usage.get("output_tokens", 0)})
        return strip_think(text)
    if provider in OPENAI_COMPAT:
        base_env, base_default, key_env = OPENAI_COMPAT[provider]
        key = os.environ.get(key_env, "")
        if not key and provider != "custom":
            raise LLMError(f"{key_env} is not set")
        base = os.environ.get(base_env, base_default)
        payload = {
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }
        if seed is not None:
            payload["seed"] = seed
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        data = _post(f"{base.rstrip('/')}/chat/completions", {"Authorization": f"Bearer {key}"}, payload, timeout)
        text = (data.get("choices") or [{}])[0].get("message", {}).get("content", "") or ""
        usage = data.get("usage", {})
        _record(provider, model, started, {"input": usage.get("prompt_tokens", 0), "output": usage.get("completion_tokens", 0)})
        return strip_think(text)
    raise LLMError(f"unknown provider '{provider}'; use ollama, anthropic, openai, groq, deepseek, openrouter, custom or mock")


def begin_calls() -> List[Dict[str, Any]]:
    calls: List[Dict[str, Any]] = []
    CALLS.set(calls)
    return calls
